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

"""Pseudospectral equations."""

import dataclasses
from typing import Optional

import jax.numpy as jnp
from jax_cfd.base import grids
from jax_cfd.spectral import forcings as spectral_forcings
from jax_cfd.spectral import time_stepping
from jax_cfd.spectral import types as spectral_types
from jax_cfd.spectral import utils as spectral_utils


@dataclasses.dataclass
class NavierStokes2D(time_stepping.ImplicitExplicitODE):
  """Breaks the Navier-Stokes equation into implicit and explicit parts.

  Implicit parts are the linear terms and explicit parts are the non-linear
  terms.

  Attributes:
    viscosity: strength of the diffusion term
    grid: underlying grid of the process
    smooth: smooth the advection term using the 2/3-rule.
    forcing_fn: forcing function, if None then no forcing is used.
    drag: strength of the drag. Set to zero for no drag.
  """
  viscosity: float
  grid: grids.Grid
  drag: float = 0.
  smooth: bool = True
  forcing_fn: Optional[spectral_types.ForcingFn] = None

  def __post_init__(self):
    self.kx, self.ky = self.grid.rfft_mesh()
    self.laplace = (jnp.pi * 2j)**2 * (self.kx**2 + self.ky**2)
    self.filter_ = spectral_utils.circular_filter_2d(self.grid)
    self.linear_term = self.viscosity * self.laplace - self.drag

  def explicit_terms(self, vorticity_hat):
    velocity_solve = spectral_utils.vorticity_to_velocity(self.grid)
    vxhat, vyhat = velocity_solve(vorticity_hat)
    vx, vy = jnp.fft.irfftn(vxhat), jnp.fft.irfftn(vyhat)

    grad_x_hat = 2j * jnp.pi * self.kx * vorticity_hat
    grad_y_hat = 2j * jnp.pi * self.ky * vorticity_hat
    grad_x, grad_y = jnp.fft.irfftn(grad_x_hat), jnp.fft.irfftn(grad_y_hat)

    advection = -(grad_x * vx + grad_y * vy)
    advection_hat = jnp.fft.rfftn(advection)

    if self.smooth is not None:
      advection_hat *= self.filter_

    terms = advection_hat

    if self.forcing_fn is not None:
      terms += jnp.fft.rfftn(self.forcing_fn(self.grid, vorticity_hat))

    return terms

  def implicit_terms(self, vorticity_hat):
    return self.linear_term * vorticity_hat

  def implicit_solve(self, vorticity_hat, time_step):
    return 1 / (1 - time_step * self.linear_term) * vorticity_hat


# pylint: disable=g-doc-args,g-doc-return-or-yield
def ForcedNavierStokes2D(viscosity, grid, smooth):
  """Sets up the flow that is used in Kochkov et al. [1].

  The authors of [1] based their work on Boffetta et al. [2].

  References:
    [1] Machine learning–accelerated computational fluid dynamics. Dmitrii
    Kochkov, Jamie A. Smith, Ayya Alieva, Qing Wang, Michael P. Brenner, Stephan
    Hoyer Proceedings of the National Academy of Sciences May 2021, 118 (21)
    e2101784118; DOI: 10.1073/pnas.2101784118.
    https://doi.org/10.1073/pnas.2101784118

    [2] Boffetta, Guido, and Robert E. Ecke. "Two-dimensional turbulence."
    Annual review of fluid mechanics 44 (2012): 427-451.
    https://doi.org/10.1146/annurev-fluid-120710-101240
  """
  return NavierStokes2D(
      viscosity,
      grid,
      drag=0.1,
      smooth=smooth,
      forcing_fn=spectral_forcings.kolmogorov_forcing_fn)
