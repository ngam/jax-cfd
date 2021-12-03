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
"""Time stepping for Navier-Stokes equations."""

from typing import Callable, Sequence, TypeVar
import jax
from jax_cfd.base import tree_math


PyTreeState = TypeVar("PyTreeState")
TimeStepFn = Callable[[PyTreeState], PyTreeState]


class ExplicitNavierStokesODE:
  """Spatially discretized version of Navier-Stokes.

  The equation is given by:

    ∂u/∂t = explicit_terms(u)
    0 = incompressibility_constraint(u)
  """

  def __init__(self, explicit_terms, pressure_projection):
    self.explicit_terms = explicit_terms
    self.pressure_projection = pressure_projection

  def explicit_terms(self, state):
    """Explicitly evaluate the ODE."""
    raise NotImplementedError

  def pressure_projection(self, state):
    """Enforce the incompressibility constraint."""
    raise NotImplementedError


def _sum(xs):
  # like builtins.sum(), but avoids using 0 as the initial value.
  result, *xs = xs
  for x in xs:
    result += x
  return result


def navier_stokes_rk(
    a: Sequence[Sequence[float]],
    b: Sequence[float],
    equation: ExplicitNavierStokesODE,
    time_step: float,
) -> TimeStepFn:
  """Create a forward Runge-Kutta time-stepper for incompressible Navier-Stokes.

  This function implements the reference method (equations 16-21), rather than
  the fast projection method, from:
    "Fast-Projection Methods for the Incompressible Navier–Stokes Equations"
    Fluids 2020, 5, 222; doi:10.3390/fluids5040222

  Args:
    a: "a" coefficients from the Butcher tableau.
    b: "b" coefficients from the Butcher tableau.
    equation: equation to use.
    time_step: overall time-step size.

  Returns:
    Function that advances one time-step forward.
  """
  # pylint: disable=invalid-name
  dt = time_step
  F = tree_math.pytree_to_vector_fun(equation.explicit_terms)
  P = tree_math.pytree_to_vector_fun(equation.pressure_projection)

  if len(a) + 1 != len(b):
    raise ValueError("inconsistent Butcher tableau")

  num_steps = len(b)

  @tree_math.vector_to_pytree_fun
  def step_fn(u0):
    u = [None] * num_steps
    k = [None] * num_steps

    u[0] = u0
    k[0] = F(u0)

    for i in range(1, num_steps):
      u_star = u0 + dt * _sum(a[i-1][j] * k[j] for j in range(i) if a[i-1][j])
      u[i] = P(u_star)
      k[i] = F(u[i])

    u_star = u0 + dt * _sum(b[j] * k[j] for j in range(num_steps) if b[j])
    u_final = P(u_star)

    return u_final

  return step_fn


def forward_euler(
    equation: ExplicitNavierStokesODE, time_step: float,
) -> TimeStepFn:
  return jax.named_call(
      navier_stokes_rk(
          a=[],
          b=[1],
          equation=equation,
          time_step=time_step,
      ),
      name="forward_euler",
  )


def midpoint_rk2(
    equation: ExplicitNavierStokesODE, time_step: float,
) -> TimeStepFn:
  return jax.named_call(
      navier_stokes_rk(
          a=[[1/2]],
          b=[0, 1],
          equation=equation,
          time_step=time_step,
      ),
      name="midpoint_rk2",
  )


def heun_rk2(
    equation: ExplicitNavierStokesODE, time_step: float,
) -> TimeStepFn:
  return jax.named_call(
      navier_stokes_rk(
          a=[[1]],
          b=[1/2, 1/2],
          equation=equation,
          time_step=time_step,
      ),
      name="heun_rk2",
  )


def classic_rk4(
    equation: ExplicitNavierStokesODE, time_step: float,
) -> TimeStepFn:
  return jax.named_call(
      navier_stokes_rk(
          a=[[1/2], [0, 1/2], [0, 0, 1]],
          b=[1/6, 1/3, 1/3, 1/6],
          equation=equation,
          time_step=time_step,
      ),
      name="classic_rk4",
  )
