from __future__ import annotations

import equinox as eqx
import jax.tree_util as jtu
from jax import Array
from jaxtyping import PyTree, ScalarLike

from ._utils import tree_str_inline
from .progress_meter import AbstractProgressMeter, NoProgressMeter, TqdmProgressMeter

__all__ = ['Options']


class Options(eqx.Module): 
    """Generic options for the quantum solvers.

    Args:
        save_states: If `True`, the state is saved at every time in `tsave`,
            otherwise only the final state is returned.
        verbose: If `True`, print information about the integration, otherwise
            nothing is printed.
        cartesian_batching: If `True`, batched arguments are treated as separated
            batch dimensions, otherwise the batching is performed over a single
            shared batched dimension.
        progress_meter: Progress meter indicating how far the solve has progressed.
            Defaults to a [tqdm](https://github.com/tqdm/tqdm) progress meter. Pass
            `None` for no output, see other options in
            [dynamiqs/progress_meter.py](https://github.com/dynamiqs/dynamiqs/blob/main/dynamiqs/progress_meter.py).
            If gradients are computed, the progress meter only displays during the
            forward pass.
        t0: Initial time. If `None`, defaults to the first time in `tsave`.
        save_extra _(function, optional)_: A function with signature
            `f(Array) -> PyTree` that takes a state as input and returns a PyTree.
            This can be used to save additional arbitrary data during the
            integration. The results are saved in extra of class Result, see [dynamiqs/result.py](https://github.com/dynamiqs/dynamiqs/blob/main/dynamiqs/result.py)
        tensorisation: (expects inequalities to be 'True')
            Explain to the program that we are dealing with
            a n dimensional object. An input could be (2,3) for an object tensorised 
            according to ((0,0),(0,1),(0,2),(1,0),(1,1),(1,2)) for instance.
        inequalities: (expects tensorisation to be given)
            For a n-dimensional object, you can give your own truncature to the
            operators. It has to be formated like a list of 2 objects list [f, param].
            param: a float.
            f: a function that has len("number of dimensions") inputs and outputs a 
            float.
            Exemple: [param = 2, f = def f(i, j): return i+j] for a 2D tensorisation
            gives [lambda i, j: i+j <= 2]
    """

    save_states: bool = True
    verbose: bool = True
    cartesian_batching: bool = True
    progress_meter: AbstractProgressMeter | None = TqdmProgressMeter()
    t0: ScalarLike | None = None
    save_extra: callable[[Array], PyTree] | None = None
    tensorisation: tuple | None = None
    inequalities: list | None = None

    def __init__(
        self,
        save_states: bool = True,
        verbose: bool = True,
        cartesian_batching: bool = True,
        progress_meter: AbstractProgressMeter | None = TqdmProgressMeter(),  # noqa: B008
        t0: ScalarLike | None = None,
        save_extra: callable[[Array], PyTree] | None = None,
        tensorisation: tuple | None = None,
        inequalities: list | None = None,
    ):
        if progress_meter is None:
            progress_meter = NoProgressMeter()

        self.save_states = save_states
        self.verbose = verbose
        self.cartesian_batching = cartesian_batching
        self.progress_meter = progress_meter
        self.t0 = t0
        self.tensorisation = tensorisation
        self.inequalities = inequalities

        # make `save_extra` a valid Pytree with `Partial`
        if save_extra is not None:
            save_extra = jtu.Partial(save_extra)
        self.save_extra = save_extra

    def __str__(self) -> str:
        return tree_str_inline(self)
