# Copyright 2021 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Implicit-explicit time stepping routines for ODEs."""

import operator
from typing import Callable, Sequence, TypeVar
from jax import tree_util


PyTreeState = TypeVar("PyTreeState")
TimeStepFn = Callable[[PyTreeState], PyTreeState]


class _InfixArithmeticWrapper:
  """A pytree wrapper to support basic infix arithmetic."""

  def __init__(self, pytree):
    self.pytree = pytree

  def __add__(self, other):
    if isinstance(other, _InfixArithmeticWrapper):
      result = tree_util.tree_map(operator.add, self.pytree, other.pytree)
    else:
      result = tree_util.tree_map(lambda x: x + other, self.pytree)
    return _InfixArithmeticWrapper(result)

  __radd__ = __add__

  def __mul__(self, other):
    if isinstance(other, _InfixArithmeticWrapper):
      result = tree_util.tree_map(operator.mul, self.pytree, other.pytree)
    else:
      result = tree_util.tree_map(lambda x: x * other, self.pytree)
    return _InfixArithmeticWrapper(result)

  __rmul__ = __mul__


def _pytree_to_infix(func):
  def wrapper(state):
    return func(_InfixArithmeticWrapper(state)).pytree
  return wrapper


def _infix_to_pytree(func):
  def wrapper(state, *aux_args):
    return _InfixArithmeticWrapper(func(state.pytree, *aux_args))
  return wrapper


class ImplicitExplicitODE:
  """Describes a set of ODEs with implicit & explicit terms.

  The equation is given by:

    ∂x/∂t = explicit_terms(x) + implicit_terms(x)

  `explicit_terms(x)` includes terms that should use explicit time-stepping and
  `implicit_terms(x)` includes terms that should be modeled implicitly.

  Typically the explicit terms are non-linear and the implicit terms are linear.
  This simplifies solves but isn't strictly necessary.
  """

  def explicit_terms(self, state: PyTreeState) -> PyTreeState:
    """Evaluates explicit terms in the ODE."""
    raise NotImplementedError

  def implicit_terms(self, state: PyTreeState) -> PyTreeState:
    """Evaluates implicit terms in the ODE."""
    raise NotImplementedError

  def implicit_solve(
      self, state: PyTreeState, step_size: float,
  ) -> PyTreeState:
    """Solves `y - step_size * implicit_terms(y) = x` for y."""
    raise NotImplementedError


def backward_forward_euler(
    equation: ImplicitExplicitODE, time_step: float,
) -> TimeStepFn:
  """Time stepping via forward and backward Euler methods.

  This method is first order accurate.

  Args:
    equation: equation to solve.
    time_step: time step.

  Returns:
    Function that performs a time step.
  """
  # pylint: disable=invalid-name
  dt = time_step
  F = _infix_to_pytree(equation.explicit_terms)
  G_inv = _infix_to_pytree(equation.implicit_solve)

  @_pytree_to_infix
  def step_fn(u0):
    g = u0 + dt * F(u0)
    u1 = G_inv(g, dt)
    return u1
  return step_fn


def crank_nicolson_rk2(
    equation: ImplicitExplicitODE, time_step: float,
) -> TimeStepFn:
  """Time stepping via Crank-Nicolson and 2nd order Runge-Kutta (Heun).

  This method is second order accurate.

  Args:
    equation: equation to solve.
    time_step: time step.

  Returns:
    Function that performs a time step.

  Reference:
    Chandler, G. J. & Kerswell, R. R. Invariant recurrent solutions embedded in
    a turbulent two-dimensional Kolmogorov flow. J. Fluid Mech. 722, 554–595
    (2013). https://doi.org/10.1017/jfm.2013.122 (Section 3)
  """
  # pylint: disable=invalid-name
  dt = time_step
  F = _infix_to_pytree(equation.explicit_terms)
  G = _infix_to_pytree(equation.implicit_terms)
  G_inv = _infix_to_pytree(equation.implicit_solve)

  @_pytree_to_infix
  def step_fn(u0):
    g = u0 + 0.5 * dt * G(u0)
    h1 = F(u0)
    u1 = G_inv(g + dt * h1, 0.5 * dt)
    h2 = 0.5 * (F(u1) + h1)
    u2 = G_inv(g + dt * h2, 0.5 * dt)
    return u2
  return step_fn


def low_storage_runge_kutta_crank_nicolson(
    alphas: Sequence[float],
    betas: Sequence[float],
    gammas: Sequence[float],
    equation: ImplicitExplicitODE,
    time_step: float,
) -> TimeStepFn:
  """Time stepping via "low-storage" Runge-Kutta and Crank-Nicolson steps.

  These scheme are second order accurate for the implicit terms, but potentially
  higher order accurate for the explicit terms. This seems to be a favorable
  tradeoff when the explicit terms dominate, e.g., for modeling turbulent
  fluids.

  Per Canuto: "[these methods] have been widely used for the time-discretization
  in applications of spectral methods."

  Args:
    alphas: alpha coefficients.
    betas: beta coefficients.
    gammas: gamma coefficients.
    equation: equation to solve.
    time_step: time step.

  Returns:
    Function that performs a time step.

  Reference:
    Canuto, C., Yousuff Hussaini, M., Quarteroni, A. & Zang, T. A.
    Spectral Methods: Evolution to Complex Geometries and Applications to
    Fluid Dynamics. (Springer Berlin Heidelberg, 2007).
    https://doi.org/10.1007/978-3-540-30728-0 (Appendix D.3)
  """
  # pylint: disable=invalid-name
  α = alphas
  β = betas
  γ = gammas
  dt = time_step
  F = _infix_to_pytree(equation.explicit_terms)
  G = _infix_to_pytree(equation.implicit_terms)
  G_inv = _infix_to_pytree(equation.implicit_solve)

  if len(alphas) - 1 != len(betas) != len(gammas):
    raise ValueError("number of RK coefficients does not match")

  @_pytree_to_infix
  def step_fn(u):
    h = 0
    for k in range(len(β)):
      h = F(u) + β[k] * h
      µ = 0.5 * dt * (α[k + 1] - α[k])
      u = G_inv(u + γ[k] * dt * h + µ * G(u), µ)
    return u
  return step_fn


def crank_nicolson_rk3(
    equation: ImplicitExplicitODE, time_step: float,
) -> TimeStepFn:
  """Time stepping via Crank-Nicolson and RK3 ("Williamson")."""
  return low_storage_runge_kutta_crank_nicolson(
      alphas=[0, 1/3, 3/4, 1],
      betas=[0, -5/9, -153/128],
      gammas=[1/3, 15/16, 8/15],
      equation=equation,
      time_step=time_step,
  )


def crank_nicolson_rk4(
    equation: ImplicitExplicitODE, time_step: float,
) -> TimeStepFn:
  """Time stepping via Crank-Nicolson and RK4 ("Carpenter-Kennedy")."""
  # pylint: disable=line-too-long
  return low_storage_runge_kutta_crank_nicolson(
      alphas=[0, 0.1496590219993, 0.3704009573644, 0.6222557631345, 0.9582821306748, 1],
      betas=[0, -0.4178904745, -1.192151694643, -1.697784692471, -1.514183444257],
      gammas=[0.1496590219993, 0.3792103129999, 0.8229550293869, 0.6994504559488, 0.1530572479681],
      equation=equation,
      time_step=time_step,
  )
