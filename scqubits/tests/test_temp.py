# test_circuit_temp.py
# meant to be run with 'pytest'
#
# This file is part of scqubits: a Python package for superconducting qubits,
# Quantum 5, 583 (2021). https://quantum-journal.org/papers/q-2021-11-17-583/
#
#    Copyright (c) 2019 and later, Jens Koch and Peter Groszkowski
#    All rights reserved.
#
#    This source code is licensed under the BSD-style license found in the
#    LICENSE file in the root directory of this source tree.
############################################################################
import scqubits as scq
import numpy as np
import os

TESTDIR, _ = os.path.split(scq.__file__)
TESTDIR = os.path.join(TESTDIR, "tests", "")
DATADIR = os.path.join(TESTDIR, "data", "")

DFC = scq.Circuit.from_yaml(
    DATADIR + "Danny_fluxonium_coupler.yaml",
    ext_basis="harmonic",
    initiate_sym_calc=False,
    basis_completion="standard",
)

closure_branches = [DFC.branches[0], DFC.branches[4], DFC.branches[-1]]
system_hierarchy = [[1], [2], [3], [4]]
# system_hierarchy = [[[[[1], [3]], [2]], [4]]]

DFC.initiate_circuit(
    closure_branches=closure_branches,
    system_hierarchy=system_hierarchy,
    subsystem_trunc_dims=[6, 6, 6, 6],
    # subsystem_trunc_dims=[[900, [[160, [[32, [6, 6]], 6]], 6]]],
)

DFC._Φ1 = 0.5 + 0.01768
DFC._Φ2 = -0.2662
DFC._Φ3 = -0.5 + 0.01768

DFC._cutoff_ext_1 = 110
DFC._cutoff_ext_2 = 110
DFC._cutoff_ext_3 = 110
DFC._cutoff_ext_4 = 110

DFC.EJ = 4.6


eigs = DFC.eigenvals()
generated_eigs = eigs - eigs[0]

print(generated_eigs)
print(scq.__file__)

def test_eigs():
    ref_eigs = np.array(
        [
            0.0,
            0.03559403678019013028688277699984610080718994140625,
            0.05819726893725007954571992740966379642486572265625,
            0.09378676436454469467207673005759716033935546875,
            4.399278742490064786352377268485724925994873046875,
            4.43488612577317109497698766062967479228973388671875,
        ]
    )
    assert np.allclose(generated_eigs, ref_eigs)
