from __future__ import annotations

import warnings
import jax
from abc import abstractmethod

import diffrax as dx
import equinox as eqx
from jax import Array
from jaxtyping import PyTree
import jax.numpy as jnp


from ..gradient import Autograd, CheckpointAutograd
from .abstract_solver import BaseSolver
from ..options import Options

from ..solver import _ODEAdaptiveStep
from .abstract_solver import State

from .._utils import cdtype



class DiffraxSolver(BaseSolver):
    stepsize_controller: dx.AbstractVar[dx.AbstractStepSizeController]
    dt0: dx.AbstractVar[float | None]
    max_steps: dx.AbstractVar[int]
    diffrax_solver: dx.AbstractVar[dx.AbstractSolver]
    terms: dx.AbstractVar[dx.AbstractTerm]
    options: Options

    def __init__(self, *args):
        # pass all init arguments to `BaseSolver`
        super().__init__(*args)

    def run(self) -> PyTree:
        # TODO: remove once complex support is stabilized in diffrax
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', UserWarning)

            # === prepare diffrax arguments
            fn = lambda t, y, args: self.save(y)  # noqa: ARG005
            subsaveat_a = dx.SubSaveAt(ts=self.ts, fn=fn)  # save solution regularly
            subsaveat_b = dx.SubSaveAt(t1=True)  # save last state
            saveat = dx.SaveAt(subs=[subsaveat_a, subsaveat_b])

            if self.gradient is None:
                adjoint = dx.RecursiveCheckpointAdjoint()
            elif isinstance(self.gradient, CheckpointAutograd):
                adjoint = dx.RecursiveCheckpointAdjoint(self.gradient.ncheckpoints)
            elif isinstance(self.gradient, Autograd):
                adjoint = dx.DirectAdjoint()

            # === solve differential equation with diffrax
            if self.options.estimator: solution = dx.diffeqsolve(
                self.terms,
                self.diffrax_solver,
                t0=self.t0,
                t1=self.ts[-1],
                dt0=self.dt0,
                y0=State(
                    self.y0, # the solution at current time
                    jnp.zeros(1, dtype = cdtype()), # the estimator at current time
                ),
                saveat=saveat,
                stepsize_controller=self.stepsize_controller,
                adjoint=adjoint,
                max_steps=self.max_steps,
            )
            else: solution = dx.diffeqsolve(
                self.terms,
                self.diffrax_solver,
                t0=self.t0,
                t1=self.ts[-1],
                dt0=self.dt0,
                y0=self.y0,
                saveat=saveat,
                stepsize_controller=self.stepsize_controller,
                adjoint=adjoint,
                max_steps=self.max_steps,
            )

        # === collect and return results
        save_a, save_b = solution.ys
        if self.options.estimator:
            saved = self.collect_saved(
            save_a, [save_b.rho[0],save_b.err[0]]
            )
            # warn the user if the estimator's tolerance has been reached
            def true_fun():
                jax.debug.print(
                    'WARNING : At this truncature of your simulation\'s size, '
                    'it\'s not possible to warranty anymore the accuracy of '
                    'your results. Try to enlarge the truncature'
                )
                jax.debug.print(
                    "estimated error = {err} > {estimator_rtol} * tolerance = {tol}", 
                    err = ((save_b.err[0][0]).real.astype(float)), tol = 
                    self.options.estimator_rtol * (self.solver.atol + 
                    jnp.linalg.norm(save_b.rho[0], ord='nuc') *
                    self.solver.rtol), estimator_rtol = self.options.estimator_rtol 
                )
                return None
            def false_fun():
                return None
            jax.lax.cond(save_b.err[0][0] > self.options.estimator_rtol *
            (self.solver.atol + 
            jnp.linalg.norm(save_b.rho[0], ord='nuc') * self.solver.rtol), 
            true_fun, false_fun)
        else: saved = self.collect_saved(save_a, save_b[0])
        return self.result(saved, infos=self.infos(solution.stats))

    @abstractmethod
    def infos(self, stats: dict[str, Array]) -> PyTree:
        pass


class FixedSolver(DiffraxSolver):
    class Infos(eqx.Module):
        nsteps: Array

        def __str__(self) -> str:
            if self.nsteps.ndim >= 1:
                # note: fixed step solvers always make the same number of steps
                return (
                    f'{int(self.nsteps.mean())} steps | infos shape {self.nsteps.shape}'
                )
            return f'{self.nsteps} steps'

    stepsize_controller: dx.AbstractStepSizeController = dx.ConstantStepSize()
    max_steps: int = 100_000  # TODO: fix hard-coded max_steps

    @property
    def dt0(self) -> float:
        return self.solver.dt

    def infos(self, stats: dict[str, Array]) -> PyTree:
        return self.Infos(stats['num_steps'])


class EulerSolver(FixedSolver):
    diffrax_solver: dx.AbstractSolver = dx.Euler()


class AdaptiveSolver(DiffraxSolver):
    class Infos(eqx.Module):
        nsteps: Array
        naccepted: Array
        nrejected: Array

        def __str__(self) -> str:
            if self.nsteps.ndim >= 1:
                return (
                    f'avg. {self.nsteps.mean()} steps ({self.naccepted.mean()}'
                    f' accepted, {self.nrejected.mean()} rejected) | infos shape'
                    f' {self.nsteps.shape}'
                )
            return (
                f'{self.nsteps} steps ({self.naccepted} accepted,'
                f' {self.nrejected} rejected)'
            )

    dt0 = None

    @property
    def stepsize_controller(self) -> dx.AbstractStepSizeController:
        return dx.PIDController(
            rtol=self.solver.rtol,
            atol=self.solver.atol,
            safety=self.solver.safety_factor,
            factormin=self.solver.min_factor,
            factormax=self.solver.max_factor,
        )

    @property
    def max_steps(self) -> int:
        return self.solver.max_steps

    def infos(self, stats: dict[str, Array]) -> PyTree:
        return self.Infos(
            stats['num_steps'], stats['num_accepted_steps'], stats['num_rejected_steps']
        )


class Dopri5Solver(AdaptiveSolver):
    diffrax_solver = dx.Dopri5()


class Dopri8Solver(AdaptiveSolver):
    diffrax_solver = dx.Dopri8()


class Tsit5Solver(AdaptiveSolver):
    diffrax_solver = dx.Tsit5()