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

"""Common types that are used throughout the spectral codes."""

from typing import Callable, Union

import jax.numpy as jnp
from jax_cfd.base import grids
import numpy as np

Array = Union[np.ndarray, jnp.DeviceArray]
StepFn = Callable[[Array], Array]
ForcingFn = Callable[[grids.Grid, Array], Array]
