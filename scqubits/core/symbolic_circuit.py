# symbolic_circuit.py
#
# This file is part of scqubits.
#
#    Copyright (c) 2019 and later, Jens Koch and Peter Groszkowski
#    All rights reserved.
#
#    This source code is licensed under the BSD-style license found in the
#    LICENSE file in the root directory of this source tree.
############################################################################

import copy
import itertools
import warnings

from symtable import Symbol
from typing import Any, Dict, List, Optional, Set, Tuple, Union

import numpy as np
import sympy
import yaml

from numpy import ndarray
from sympy import symbols

import scqubits.io_utils.fileio_serializers as serializers

from scqubits.utils.misc import is_float_string


def process_word(word: str) -> Union[float, symbols]:
    if is_float_string(word):
        return float(word)
    return symbols(word)


def parse_branch_parameter(word: str) -> Union[List[float], List[Union[Symbol, float]]]:
    """
    If the string word only has a number, its float value is returned. Else, if the word
    has the form "EJ=10", no spaces before or after =, it will return the Symbol object
    EJ and the float 10.

    Parameters
    ----------
    word:
        Should be a number "0.123" or a variable assignment of the form "EJ=10"

    Returns
    -------
        Returns a float if the string only has a number, else returns a tuple
        of format `(Symbol, float)`.

    Raises
    ------
    Exception
        If the variable is not initialized.
    Exception
        if space was used before or after "="
    Exception
        Error if init value for a variable is not float.
    """
    if not is_float_string(word):
        if len(word.split("=")) > 2:
            raise Exception(
                "Proper syntax is not followed please follow the documentation."
            )
        if len(word.split("=")) == 2:
            var_str, init_val = word.split("=")
            return [process_word(var_str), process_word(init_val)]
        elif len(word.split("=")) == 1:
            return [process_word(word)]
    else:
        return [float(word)]


class Node:
    """
    Class representing a circuit node, and handled by `Circuit`. The attribute
    `<Node>.branches` is a list of `Branch` objects containing all branches connected to
    the node.

    Parameters
    ----------
    id: int
        integer identifier of the node
    marker: int
        An internal attribute used to group nodes and identify sub-circuits in the
        method independent_modes.
    """

    def __init__(self, id: int, marker: int):
        self.id = id
        self.marker = marker
        self.branches: List[Branch] = []

    def __str__(self) -> str:
        return "Node {}".format(self.id)

    def __repr__(self) -> str:
        return "Node({})".format(self.id)

    def connected_nodes(self, branch_type: str) -> List["Node"]:
        """
        Returns a list of all nodes directly connected by branches to the current
        node, either considering all branches or a specified `branch_type`:
        "C", "L", "JJ", "all" for capacitive, inductive, Josephson junction,
        or all types of branches.
        """
        result = []
        if branch_type == "all":
            branch_list = self.branches
        else:
            branch_list = [
                branch for branch in self.branches if branch.type == branch_type
            ]
        for branch in branch_list:
            if branch.nodes[0].id == self.id:
                result.append(branch.nodes[1])
            else:
                result.append(branch.nodes[0])
        return result

    def is_ground(self) -> bool:
        """
        Returns a bool if the node is a ground node. It is ground if the id is set to 0.
        """
        return True if self.id == 0 else False

    def __deepcopy__(self, memo):
        cls = self.__class__
        result = cls.__new__(cls)
        memo[id(self)] = result
        for k, v in self.__dict__.items():
            setattr(result, k, copy.deepcopy(v, memo))
        return result


class Branch:
    """
    Class describing a circuit branch, used in the Circuit class.

    Parameters
    ----------
    n_i, n_f:
        initial and final nodes connected by this branch;
    branch_type:
        is the type of this Branch, example "C","JJ" or "L"
    parameters:
        dictionary of parameters for the branch, namely for
        capacitance: {"EC":  <value>};
        for inductance: {"EL": <value>};
        for Josephson Junction: {"EJ": <value>, "ECJ": <value>}

    Examples
    --------
    `Branch("C", Node(1, 0), Node(2, 0))`
    is a capacitive branch connecting the nodes with indices 0 and 1.
    """

    def __init__(
        self,
        n_i: Node,
        n_f: Node,
        branch_type: str,
        parameters: Optional[Dict[str, float]] = None,
    ):
        self.nodes = (n_i, n_f)
        self.type = branch_type
        self.parameters = parameters
        # store info of current branch inside the provided nodes
        # setting the parameters if it is provided
        if parameters is not None:
            self.set_parameters(parameters)
        # TODO: discuss - this is an unexpected side effect - Each node is also updated
        #  when a new branch is created. This helps for example when we want to get the
        #  list of all branches connected to a single node. Makes it easier to write
        #  code, but definitely makes it more complicated to deal with.
        self.nodes[0].branches.append(self)
        self.nodes[1].branches.append(self)

    def __str__(self) -> str:
        return (
            "Branch "
            + self.type
            + " connecting nodes: ("
            + str(self.nodes[0].id)
            + ","
            + str(self.nodes[1].id)
            + "); "
            + str(self.parameters)
        )

    def __repr__(self) -> str:
        return "Branch({}, {}, {})".format(
            self.type, self.nodes[0].id, self.nodes[1].id
        )

    def set_parameters(self, parameters) -> None:
        if self.type in ["C", "L"]:
            self.parameters = {"E" + self.type: parameters[0]}
        elif self.type in ["JJ", "JJ2"]:
            self.parameters = {"EJ": parameters[0], "ECJ": parameters[1]}

    def node_ids(self) -> Tuple[int, int]:
        return (self.nodes[0].id, self.nodes[1].id)

    def is_connected(self, branch) -> bool:
        """Returns a boolean indicating whether the current branch is
        connected to the given `branch`"""
        distinct_node_count = len(set(self.nodes + branch.nodes))
        if distinct_node_count < 4:
            return True
        return False

    def common_node(self, branch) -> Set[Node]:
        """Returns the common nodes between self and the `branch` given as input"""
        return set(self.nodes) & set(branch.nodes)

    def __deepcopy__(self, memo):
        cls = self.__class__
        result = cls.__new__(cls)
        memo[id(self)] = result
        for k, v in self.__dict__.items():
            setattr(result, k, copy.deepcopy(v, memo))
        return result


class SymbolicCircuit(serializers.Serializable):
    r"""
    Describes a circuit consisting of nodes and branches.

    Examples
    --------
    For a transmon qubit, the input file reads:
        ```
        # file_name: transmon_num.inp
        nodes: 2
        branches:
        C	1,2	1
        JJ	1,2	1	10
        ```

    The `Circuit` object can be initiated using:
        `Circuit.from_input_file("transmon_num.inp")`

    Parameters
    ----------
    nodes_list:
        List of nodes in the circuit
    branches_list:
        List of branches connecting the above set of nodes.
    basis:
        string; should be "simple" or "standard" used to choose a type of basis for
        completing the transformation matrix. Set to "simple" by default. Name needs to
        be updated.
    ground_node:
        If the circuit is grounded, the ground node is treated separately and should be
        provided to this parameter.
    initiate_sym_calc:
        Boolean, set to True by default. Initiates the object attributes by calling the
        function initiate_symboliccircuit method when set to True. Set to False for
        debugging.
    """

    def __init__(
        self,
        nodes_list: List[Node],
        branches_list: List[Branch],
        branch_var_dict: dict,
        basis_completion: str = "simple",
        ground_node: Optional[Node] = None,
        initiate_sym_calc: bool = True,
        input_string: str = "",
    ):
        self.branches = branches_list
        self.nodes = nodes_list
        self.input_string = input_string

        self._sys_type = type(self).__name__  # for object description

        # attributes set by methods
        self.transformation_matrix: ndarray = None

        self.var_categories: Optional[List[int]] = None
        self.external_fluxes: List[Symbol] = []
        self.closure_branches: List[Branch] = []

        self.param_vars: List[Symbol] = list(branch_var_dict.keys())
        self.param_init_vals: List[float] = list(branch_var_dict.values())

        self.hamiltonian_symbolic: Optional[sympy.Expr] = None
        # to store the internally used lagrangian
        self._lagrangian_symbolic: Optional[sympy.Expr] = None
        self.lagrangian_symbolic: Optional[sympy.Expr] = None
        # symbolic lagrangian in terms of untransformed generalized flux variables
        self.lagrangian_node_vars: Optional[sympy.Expr] = None
        # symbolic expression for potential energy
        self.potential_symbolic: Optional[sympy.Expr] = None

        # parameters for grounding the circuit
        self.ground_node = ground_node
        self.is_grounded = bool(self.ground_node)

        # TODO comments in the following two lines are not helpful - Needs renaming and
        # some refactoring in the method variable_transformation_matrix
        # parameter for chosing the basis - needs to be rewritten
        self.basis_completion = (
            basis_completion  # default, the other choice is standard
        )

        self.initiate_sym_calc = initiate_sym_calc

        # Calling the function to initiate the calss variables
        if initiate_sym_calc:
            self.initiate_symboliccircuit()

    def is_any_branch_parameter_symbolic(self):
        return True if len(self.param_vars) > 0 else False

    def initiate_symboliccircuit(
        self, transformation_matrix=None, closure_branches=None
    ):
        """
        Method to initialize the CustomQCircuit instance and initialize all the
        attributes needed before it can be passed on to AnalyzeQCircuit.

        Parameters
        ----------
        transformation_matrix:
            Takes an ndarray and is used to set an alternative transformation matrix
            than the one generated by the method variable_transformation_matrix.
        """
        # if the user provides a transformation matrix
        if transformation_matrix is not None:
            self.var_categories = self.check_transformation_matrix(
                transformation_matrix
            )
            self.transformation_matrix = transformation_matrix
        # calculate the transformation matrix and identify the boundary conditions if
        # the user does not provide a custom transformation matrix
        else:
            (
                self.transformation_matrix,
                self.var_categories,
            ) = self.variable_transformation_matrix()

        # find the closure branches in the circuit
        self.closure_branches = closure_branches or self._closure_branches()
        # setting external flux and offset charge variables
        self._set_external_fluxes(closure_branches=closure_branches)
        self._set_offset_charges()
        # setting the branch parameter variables
        # self._set_param_vars()
        # Calculate the Lagrangian
        (
            self._lagrangian_symbolic,
            self.potential_symbolic,
            self.lagrangian_node_vars,
        ) = self.generate_symbolic_lagrangian()

        # replacing energies with capacitances in the kinetic energy of the Lagrangian
        (
            self.lagrangian_symbolic,
            self.lagrangian_node_vars,
        ) = self._replace_energies_with_capacitances_L()

        # calculating the Hamiltonian directly when the number of nodes is less than 3
        if (
            len(self.nodes) <= 3
        ):  # only calculate the symbolic hamiltonian when the number of nodes is less
            # than 3. Else, the calculation will be skipped to the end when numerical
            # Hamiltonian of the circuit is requested.
            self.hamiltonian_symbolic = self.generate_symbolic_hamiltonian()

    def _replace_energies_with_capacitances_L(self):
        """
        Method replaces the energies in the Lagrangian with capacitances which are
        arbitrarily generated to make sure that the Lagrangian looks dimensionally
        correct.
        """
        # Replacing energies with capacitances if any branch parameters are symbolic
        L = self._lagrangian_symbolic.expand()
        L_old = self.lagrangian_node_vars
        if self.is_any_branch_parameter_symbolic():
            # finding the unique capacitances
            uniq_capacitances = []
            element_param = {"C": "EC", "JJ": "ECJ", "JJ2": "ECJ"}
            for c, b in enumerate(
                [
                    t
                    for t in self.branches
                    if t.type == "C" or t.type == "JJ" or t.type == "JJ2"
                ]
            ):
                if len(set(b.nodes)) > 1:  # check to see if branch is shorted
                    if b.parameters[element_param[b.type]] not in uniq_capacitances:
                        uniq_capacitances.append(b.parameters[element_param[b.type]])

            for index, var in enumerate(uniq_capacitances):
                L = L.subs(var, 1 / (8 * symbols("C" + str(index + 1))))
                L_old = L_old.subs(var, 1 / (8 * symbols("C" + str(index + 1))))
        return L, L_old

    # TODO: what's going on here? - I thought something like this was necessary for
    #  serialize to make sure we can store this object onto a file in the HDD.
    @staticmethod
    def default_params() -> Dict[str, Any]:
        # return {"EJ": 15.0, "EC": 0.3, "ng": 0.0, "ncut": 30, "truncated_dim": 10}

        return {}

    @staticmethod
    def are_branchsets_disconnected(
        branch_list1: List[Branch], branch_list2: List[Branch]
    ) -> bool:
        """
        Determines whether two sets of branches are disconnected.

        Parameters
        ----------
        branch_list1 : List[Branch]
        branch_list2 : List[Branch]

        Returns
        -------
        bool
            Returns True if the branches have a connection, else False
        """
        node_array1 = np.array([branch.node_ids() for branch in branch_list1]).flatten()
        node_array2 = np.array([branch.node_ids() for branch in branch_list2]).flatten()
        return np.intersect1d(node_array1, node_array2).size == 0

    @staticmethod
    def _parse_nodes(num_nodes) -> List[Node]:
        return [Node(idx, 0) for idx in range(1, num_nodes + 1)]

    @staticmethod
    def _parse_branches(
        branches_list, nodes: List[Node]
    ) -> Tuple[
        List[Branch], Optional[Node], Dict[Union[Any, Symbol], Union[Any, float]]
    ]:

        node_count = len(nodes)
        is_grounded = False
        ground_node = None

        branches = []
        branch_var_dict = (
            {}
        )  # dictionary which stores the init values of all the variables defined in
        # input string
        for branch_list_input in branches_list:

            branch_type = branch_list_input[0]
            node_id1, node_id2 = branch_list_input[1], branch_list_input[2]

            if (branch_type == "JJ" or branch_type == "JJ2") and len(
                branch_list_input
            ) != 5:
                raise Exception(
                    "Incorrect number of parameters specified for the JJ input in the "
                    "line: " + str(branch_list_input)
                )
            elif (branch_type == "L" or branch_type == "C") and len(
                branch_list_input
            ) != 4:
                raise Exception(
                    "Incorrect number of parameters specified for the C or L input in "
                    "the line: " + str(branch_list_input)
                )

            if node_id1 * node_id2 == 0 and not is_grounded:
                # Make a ground node when any of the branches in the input file has 0 as
                # one of the nodes. This implies that ground node is included in the
                # circuit.
                # input file
                # TODO: explain why? - The node count includes the set of all nodes
                #  including ground node. But, the numer of nodes in the input file
                #  should not include the ground node. I will change this unnecessary
                #  complication by refactoring that method slightly.
                node_count += 1
                ground_node = Node(0, 0)
                is_grounded = True

            if branch_type in ["JJ", "JJ2"]:
                branch_params = []
                for word in branch_list_input[3:5]:
                    params = parse_branch_parameter(word)
                    if len(params) == 1:
                        if (
                            type(params[0]) is not float
                            and params[0] not in branch_var_dict
                        ):
                            raise Exception(
                                "The parameter "
                                + str(str(params[0]) + " has not been initialized.")
                            )
                        branch_params.append(params[0])
                    else:
                        branch_var_dict[params[0]] = params[1]
                        branch_params.append(params[0])

                parameters = branch_params.copy()
            else:
                params = parse_branch_parameter(branch_list_input[3])
                branch_params = []
                if len(params) == 1:
                    if (
                        type(params[0]) is not float
                        and params[0] not in branch_var_dict
                    ):
                        raise Exception(
                            "The parameter "
                            + str(params[0])
                            + " has not been initialized."
                        )
                    branch_params.append(params[0])
                else:
                    branch_var_dict[params[0]] = params[1]
                    branch_params.append(params[0])
                parameters = branch_params

            if node_id1 == 0:
                branches.append(
                    Branch(
                        ground_node,
                        nodes[node_id2 - 1],
                        branch_type,
                        parameters,
                    )
                )
            elif node_id2 == 0:
                branches.append(
                    Branch(
                        nodes[node_id1 - 1],
                        ground_node,
                        branch_type,
                        parameters,
                    )
                )
            else:
                branches.append(
                    Branch(
                        nodes[node_id1 - 1],
                        nodes[node_id2 - 1],
                        branch_type,
                        parameters,
                    )
                )
        return branches, ground_node, branch_var_dict

    @classmethod
    def from_yaml(
        cls,
        input_string: str,
        is_file: bool = True,
        basis_completion: str = "simple",
        initiate_sym_calc: bool = True,
    ):
        """
        Constructs the instance of Circuit from an input string. Here is an example of
        an input string that is used to initiate an object of the
        class `SymbolicCircuit`:

            ```
            nodes: 7
            branches:
            JJ 0,1 5 1
            JJ 1,2 5 1
            JJ 3,4 EJ ECJ
            JJ 5,6 4 1
            L 2,3 1
            L 4,0 2
            L 3,5 3
            L 6,7 4
            C 3,4 5
            C 5,6 1
            C 7,0 1
            ```
        # TODO docstring needs updates

        Parameters
        ----------
        input_string:
            String describing the number of nodes and branches connecting then along
            with their parameters
        basis_completion:
            choices: "simple" or "standard"; used to choose a type of basis
            for completing the transformation matrix. Set to "simple" by default.
        initiate_sym_calc:
            set to True by default. Initiates the object attributes by calling
            the function `initiate_symboliccircuit` method when set to True.
            Set to False for debugging.

        Returns
        -------
            Instance of the class `SymbolicCircuit`
        """
        if is_file:
            file = open(input_string, "r")
            circuit_desc = file.read()
            file.close()
        else:
            circuit_desc = input_string

        input_dictionary = yaml.load(circuit_desc, Loader=yaml.FullLoader)

        nodes = cls._parse_nodes(input_dictionary["nodes"])
        branches, ground_node, branch_var_dict = cls._parse_branches(
            input_dictionary["branches"], nodes
        )

        circuit = cls(
            nodes,
            branches,
            ground_node=ground_node,
            branch_var_dict=branch_var_dict,
            basis_completion=basis_completion,
            initiate_sym_calc=initiate_sym_calc,
            input_string=circuit_desc,
        )

        return circuit

    def _independent_modes(
        self,
        branch_subset: List[Branch],
        single_nodes: bool = True,
        basisvec_entries: List[int] = [1, 0],
    ):
        """
        Returns the vectors which span a subspace where there is no generalized flux
        difference across the branches present in the branch_subset.

        Parameters
        ----------
        single_nodes:
            if the single nodes are taken into consideration for basis vectors.
        """
        nodes_copy = self.nodes.copy()  # copying self.nodes as it is being modified

        if self.is_grounded:  # needed as ground node is not included in self.nodes
            nodes_copy.append(self.ground_node)

        for node in nodes_copy:  # reset the node markers
            node.marker = 0

        # step 2: finding the maximum connected set of independent branches in
        # branch_subset, then identifying the sets of nodes in each of those sets
        branch_subset_copy = branch_subset.copy()

        max_connected_subgraphs = []  # list containing the maximum connected subgraphs

        while (
            len(branch_subset_copy) > 0
        ):  # while loop ends when all the branches are sorted
            b_0 = branch_subset_copy.pop(0)
            max_connected_subgraph = [b_0]

            while not self.are_branchsets_disconnected(
                max_connected_subgraph, branch_subset_copy
            ):
                for b1 in branch_subset_copy:
                    for b2 in max_connected_subgraph:
                        if b1.is_connected(b2):
                            max_connected_subgraph.append(b1)
                            branch_subset_copy.remove(b1)
                            break
            max_connected_subgraphs.append(max_connected_subgraph)

        # finding the nodes in each of the maximum connected subgraph
        nodes_in_max_connected_branchsets = [
            list(set(sum([branch.nodes for branch in branch_set], ())))
            for branch_set in max_connected_subgraphs
        ]

        # using node.marker to mark the maximum connected subgraph to which a node
        # belongs
        for node_set_index, node_set in enumerate(nodes_in_max_connected_branchsets):
            for node in node_set:
                node.marker = (
                    -1 if any([n.is_ground() for n in node_set]) else node_set_index + 1
                )

        node_branch_set_indices = [
            node.marker for node in nodes_copy
        ]  # identifies which node belongs to which maximum connected subgraphs;
        # different numbers on two nodes indicates that they are not connected through
        # any of the branches in branch_subset. 0 implies the node does not belong to
        # any of the branches in max connected branch subsets and -1 implies the max
        # connected branch set is connected to ground.

        # step 3: Finding the linearly independent vectors spanning the vector space
        # represented by branch_set_index
        basis = []

        unique_branch_set_markers = list(set(node_branch_set_indices))
        # removing the marker -1 as it is grounded.
        branch_set_markers_ungrounded = [
            marker for marker in unique_branch_set_markers if marker != -1
        ]

        for index in branch_set_markers_ungrounded:
            basis.append(
                [
                    basisvec_entries[0] if i == index else basisvec_entries[1]
                    for i in node_branch_set_indices
                ]
            )

        if single_nodes:  # taking the case where the node_branch_set_index is 0
            single_node_modes = []
            if node_branch_set_indices.count(0) > 0:
                ref_vector = [
                    basisvec_entries[0] if i == 0 else basisvec_entries[1]
                    for i in node_branch_set_indices
                ]
                positions = [
                    index
                    for index, num in enumerate(ref_vector)
                    if num == basisvec_entries[0]
                ]
                for pos in positions:
                    single_node_modes.append(
                        [
                            basisvec_entries[0] if x == pos else basisvec_entries[1]
                            for x, num in enumerate(node_branch_set_indices)
                        ]
                    )

            for mode in single_node_modes:
                mat = np.array(basis + [mode])
                if np.linalg.matrix_rank(mat) == len(mat):
                    basis.append(mode)

        if (
            self.is_grounded
        ):  # if grounded remove the last column and first row corresponding to the
            basis = [i[:-1] for i in basis]

        return basis

    @staticmethod
    def _mode_in_subspace(mode, subspace) -> bool:
        """
        Method to check if the vector mode is a part of the subspace provided as a set
        of vectors

        Parameters
        ----------
        mode:
            numpy ndarray of one dimension.
        subspace:
            numpy ndarray which represents a collection of basis vectors for a vector
            subspace
        """
        if len(subspace) == 0:
            return False
        matrix = np.vstack([subspace, np.array(mode)])
        return np.linalg.matrix_rank(matrix) == len(subspace)

    def check_transformation_matrix(self, transformation_matrix: ndarray):
        """
        Method to identify the different modes in the transformation matrix provided by
        the user.

        Parameters
        ----------
        transformation_matrix :
            numpy ndarray which is a square matrix having the dimensions of the number
            of nodes present in the circuit.

        Returns
        -------
            A dictionary of lists which has the variable indices classified with
            var indices corresponding to the rows of the transformation matrix
        """
        # basic check to see if the matrix is invertible
        if np.linalg.det(transformation_matrix) == 0:
            raise Exception("The transformation matrix provided is not invertible")

        # find all the different types of modes present in the circuit.

        # *************************** Finding the Periodic Modes ##################
        selected_branches = [branch for branch in self.branches if branch.type == "L"]
        periodic_modes = self._independent_modes(selected_branches)

        # *************************** Finding the frozen modes ##################
        selected_branches = [branch for branch in self.branches if branch.type != "L"]
        frozen_modes = self._independent_modes(selected_branches, single_nodes=True)

        # *************************** Finding the Cyclic Modes ****************
        selected_branches = [branch for branch in self.branches if branch.type != "C"]
        cyclic_modes = self._independent_modes(selected_branches)

        # ************************ Finding the extended Modes ****************
        # extended_modes = self.get_extended_modes()

        # ***************************# Finding the LC Modes ****************
        selected_branches = [branch for branch in self.branches if branch.type == "JJ"]
        LC_modes = self._independent_modes(selected_branches, single_nodes=False)

        # ******************* including the Σ mode ****************
        Σ = [1] * len(self.nodes)
        if not self.is_grounded:  # only append if the circuit is not grounded
            # check to see if the vectors are still independent
            if self._mode_in_subspace(Σ, frozen_modes):
                frozen_modes = frozen_modes[1:] + [Σ]
            else:
                frozen_modes.append(Σ)

        # *********** Adding periodic, cyclic and extended modes to frozen ************
        modes = []  # starting with the frozen modes

        for m in (
            frozen_modes + cyclic_modes + periodic_modes + LC_modes  # + extended_modes
        ):  # This order is important
            if not self._mode_in_subspace(m, modes):
                modes.append(m)

        for m in LC_modes:  # adding the LC modes to the basis
            mat = np.array(modes + [m])
            if not self._mode_in_subspace(m, modes):
                modes.append(m)

        var_categories_circuit: Dict[str, list] = {
            "periodic": [],
            "extended": [],
            "cyclic": [],
            "frozen": [],
            "osc": [],
        }

        for x, mode in enumerate(modes):
            # calculate the number of periodic modes
            if self._mode_in_subspace(Σ, [mode]) and not self.is_grounded:
                continue

            if self._mode_in_subspace(mode, frozen_modes):
                var_categories_circuit["frozen"].append(x + 1)
                continue

            if self._mode_in_subspace(mode, cyclic_modes):
                var_categories_circuit["cyclic"].append(x + 1)
                continue

            if self._mode_in_subspace(mode, periodic_modes):
                var_categories_circuit["periodic"].append(x + 1)
                continue

            if self._mode_in_subspace(mode, LC_modes):
                var_categories_circuit["osc"].append(x + 1)
            # Any mode which survived the above conditionals is an extended mode
            var_categories_circuit["extended"].append(x + 1)

        # Classifying the modes given in the transformation by the user

        user_given_modes = transformation_matrix.transpose()

        var_categories_user: Dict[str, list] = {
            "periodic": [],
            "extended": [],
            "cyclic": [],
            "frozen": [],
            "osc": [],
        }

        for x, mode in enumerate(user_given_modes):
            # calculate the number of periodic modes
            if self._mode_in_subspace(Σ, [mode]) and not self.is_grounded:
                continue

            if self._mode_in_subspace(mode, frozen_modes):
                var_categories_user["frozen"].append(x + 1)
                continue

            if self._mode_in_subspace(mode, cyclic_modes):
                var_categories_user["cyclic"].append(x + 1)
                continue

            if self._mode_in_subspace(mode, periodic_modes):
                var_categories_user["periodic"].append(x + 1)
                continue

            if self._mode_in_subspace(mode, LC_modes):
                var_categories_user["osc"].append(x + 1)

            # Any mode which survived the above conditionals is an extended mode
            var_categories_user["extended"].append(x + 1)

        # comparing the modes in the user defined and the code generated transformation

        mode_types = ["periodic", "extended", "cyclic", "frozen", "osc"]

        for mode_type in mode_types:
            num_extra_modes = len(var_categories_circuit[mode_type]) - len(
                var_categories_user[mode_type]
            )
            if num_extra_modes > 0:
                warnings.warn(
                    "Number of extra "
                    + mode_type
                    + " modes found: "
                    + str(num_extra_modes)
                    + "\n"
                )

        return var_categories_user

    def variable_transformation_matrix(self) -> Tuple[ndarray, Dict[str, List[int]]]:
        """
        Evaluates the boundary conditions and constructs the variable transformation
        matrix, which is returned along with the dictionary `var_categories` which
        classifies the types of variables present in the circuit.

        Returns
        -------
            tuple of transformation matrix for the node variables and `var_categories`
            dict which classifies the variable types for each variable index
        """

        # ****************  Finding the Periodic Modes ****************
        selected_branches = [branch for branch in self.branches if branch.type == "L"]
        periodic_modes = self._independent_modes(selected_branches)

        # ****************  Finding the frozen modes ****************
        selected_branches = [branch for branch in self.branches if branch.type != "L"]
        frozen_modes = self._independent_modes(selected_branches, single_nodes=True)

        # **************** Finding the Cyclic Modes ****************
        selected_branches = [branch for branch in self.branches if branch.type != "C"]
        cyclic_modes = self._independent_modes(selected_branches)

        # **************** Finding the extended Modes ****************
        # extended_modes = self.get_extended_modes()

        # ****************  including the Σ mode ****************
        Σ = [1] * len(self.nodes)
        if not self.is_grounded:  # only append if the circuit is not grounded
            mat = np.array(frozen_modes + [Σ])
            # check to see if the vectors are still independent
            if np.linalg.matrix_rank(mat) < len(frozen_modes) + 1:
                frozen_modes = frozen_modes[1:] + [Σ]
            else:
                frozen_modes.append(Σ)

        # **************** Finding the LC Modes ****************
        selected_branches = [branch for branch in self.branches if branch.type == "JJ"]
        LC_modes = self._independent_modes(
            selected_branches, single_nodes=False, basisvec_entries=[-1, 1]
        )

        # **************** Adding frozen, cyclic, periodic , LC and extended modes ****
        modes = []  # starting with an empty list

        for m in (
            frozen_modes + cyclic_modes + periodic_modes + LC_modes  # + extended_modes
        ):  # This order is important
            mat = np.array(modes + [m])
            if np.linalg.matrix_rank(mat) == len(mat):
                modes.append(m)

        # ********** Completing the Basis ****************
        # step 4: construct the new set of basis vectors

        # constructing a standard basis
        node_count = len(self.nodes)
        standard_basis = [np.ones(node_count)]

        vector_ref = np.zeros(node_count)
        if node_count > 2:
            vector_ref[: node_count - 2] = 1
        else:
            vector_ref[: node_count - 1] = 1

        vector_set = list((itertools.permutations(vector_ref, node_count)))
        item = 0
        while np.linalg.matrix_rank(np.array(standard_basis)) < node_count:
            a = vector_set[item]
            item += 1
            mat = np.array(standard_basis + [a])
            if np.linalg.matrix_rank(mat) == len(mat):
                standard_basis = standard_basis + [list(a)]

        standard_basis = np.array(standard_basis)

        if self.basis_completion == "standard":
            standard_basis = np.identity(len(self.nodes))

        new_basis = modes.copy()

        for m in standard_basis:  # completing the basis
            mat = np.array([i for i in new_basis] + [m])
            if np.linalg.matrix_rank(mat) == len(mat):
                new_basis.append(m)

        new_basis = np.array(new_basis)
        # new_basis = np.array(modes)

        # sorting the basis so that the cyclic, periodic and frozen variables occur at
        # the beginning.
        if not self.is_grounded:
            pos_Σ = [i for i in range(len(new_basis)) if new_basis[i].tolist() == Σ]
        else:
            pos_Σ = []

        pos_cyclic = [
            i
            for i in range(len(new_basis))
            if i not in pos_Σ
            if new_basis[i].tolist() in cyclic_modes
        ]
        pos_periodic = [
            i
            for i in range(len(new_basis))
            if i not in pos_Σ
            if i not in pos_cyclic
            if new_basis[i].tolist() in periodic_modes
        ]
        pos_frozen = [
            i
            for i in range(len(new_basis))
            if i not in pos_Σ
            if i not in pos_cyclic
            if i not in pos_periodic
            if new_basis[i].tolist() in frozen_modes
        ]
        pos_osc = [
            i
            for i in range(len(new_basis))
            if i not in pos_Σ
            if i not in pos_cyclic
            if i not in pos_periodic
            if i not in pos_frozen
            if new_basis[i].tolist() in LC_modes
        ]
        pos_rest = [
            i
            for i in range(len(new_basis))
            if i not in pos_Σ
            if i not in pos_cyclic
            if i not in pos_periodic
            if i not in pos_frozen
        ]
        pos_list = pos_periodic + pos_rest + pos_cyclic + pos_frozen + pos_Σ
        # transforming the new_basis matrix
        new_basis = new_basis[pos_list].T

        # saving the vatriable identification to a dict
        var_categories = {
            "periodic": [
                i + 1 for i in range(len(pos_list)) if pos_list[i] in pos_periodic
            ],
            "extended": [
                i + 1 for i in range(len(pos_list)) if pos_list[i] in pos_rest
            ],
            "cyclic": [
                i + 1 for i in range(len(pos_list)) if pos_list[i] in pos_cyclic
            ],
            "frozen": [
                i + 1 for i in range(len(pos_list)) if pos_list[i] in pos_frozen
            ],
            "osc": [i + 1 for i in range(len(pos_list)) if pos_list[i] in pos_osc],
        }

        return np.array(new_basis), var_categories

    def _set_param_vars(self):
        """
        Sets the attribute param_vars.
        """

        # set param_vars
        parameters = []  # list containing all the Ec's, El's ,Ej's and Ecj's
        for b in self.branches:
            if b.type == "JJ" or b.type == "JJ2":
                parameters.append(b.parameters["EJ"])
                parameters.append(b.parameters["ECJ"])
            elif b.type == "L":
                parameters.append(b.parameters["EL"])
            elif b.type == "C":
                parameters.append(b.parameters["EC"])
        parameters = [
            param
            for param in list(set(parameters))
            if type(param) == sympy.core.symbol.Symbol
        ]

        self.param_vars = parameters

    def update_param_init_val(self, param_name, value):
        """
        Updates the param init val for param_name
        """
        for index, param in enumerate(self.param_vars):
            if param_name == param.name:
                self.param_init_vals[index] = value
                break

    def _junction_terms(self):
        terms = 0
        # looping over all the junction terms
        junction_branches = [branch for branch in self.branches if branch.type == "JJ"]
        for jj_branch in junction_branches:
            # adding external flux
            phi_ext = 0
            if jj_branch in self.closure_branches:
                index = self.closure_branches.index(jj_branch)
                phi_ext += self.external_fluxes[index]

            # if loop to check for the presence of ground node
            if jj_branch.nodes[1].id == 0:
                terms += -jj_branch.parameters["EJ"] * sympy.cos(
                    -symbols("φ" + str(jj_branch.nodes[0].id)) + phi_ext
                )
            elif jj_branch.nodes[0].id == 0:
                terms += -jj_branch.parameters["EJ"] * sympy.cos(
                    symbols("φ" + str(jj_branch.nodes[1].id)) + phi_ext
                )
            else:
                terms += -jj_branch.parameters["EJ"] * sympy.cos(
                    symbols("φ" + str(jj_branch.nodes[1].id))
                    - symbols("φ" + str(jj_branch.nodes[0].id))
                    + phi_ext
                )
        return terms

    def _JJ2_terms(self):
        terms = 0
        # looping over all the JJ2 branches
        for jj2_branch in [t for t in self.branches if t.type == "JJ2"]:
            # adding external flux
            phi_ext = 0
            if jj2_branch in self.closure_branches:
                index = self.closure_branches.index(jj2_branch)
                phi_ext += self.external_fluxes[index]

            # if loop to check for the presence of ground node
            if jj2_branch.nodes[1].id == 0:
                terms += -jj2_branch.parameters["EJ"] * sympy.cos(
                    2 * (-symbols("φ" + str(jj2_branch.nodes[0].id)) + phi_ext)
                )
            elif jj2_branch.nodes[0].id == 0:
                terms += -jj2_branch.parameters["EJ"] * sympy.cos(
                    2 * (symbols("φ" + str(jj2_branch.nodes[1].id)) + phi_ext)
                )
            else:
                terms += -jj2_branch.parameters["EJ"] * sympy.cos(
                    2
                    * (
                        symbols("φ" + str(jj2_branch.nodes[1].id))
                        - symbols("φ" + str(jj2_branch.nodes[0].id))
                        + phi_ext
                    )
                )
        return terms

    def _capacitance_matrix(self, substitute_params: bool = False):
        """
        Generate a capacitance matrix for the circuit

        Parameters
        ----------
        substitute_params:
            when set to True all the symbolic branch parameters are substituted with
            their corresponding attributes in float, by default False

        Returns
        -------
        _type_
            _description_
        """
        branches_with_capacitance = [
            branch for branch in self.branches if branch.type in ["C", "JJ", "JJ2"]
        ]
        capacitance_param_for_branch_type = {
            "C": "EC",
            "JJ": "ECJ",
            "JJ2": "ECJ",
        }

        param_init_vals_dict = dict(zip(self.param_vars, self.param_init_vals))

        # filling the non-diagonal entries
        if not self.is_grounded:
            num_nodes = len(self.nodes)
            if not self.is_any_branch_parameter_symbolic() or substitute_params:
                C_mat = np.zeros([num_nodes, num_nodes])
            else:
                C_mat = sympy.zeros(num_nodes)
        else:
            num_nodes = len(self.nodes) + 1
            if not self.is_any_branch_parameter_symbolic() or substitute_params:
                C_mat = np.zeros([num_nodes, num_nodes])
            else:
                C_mat = sympy.zeros(num_nodes)

        for branch in branches_with_capacitance:
            if len(set(branch.nodes)) > 1:  # branch if shorted is not considered
                capacitance = branch.parameters[
                    capacitance_param_for_branch_type[branch.type]
                ]
                if type(capacitance) != float and substitute_params:
                    capacitance = param_init_vals_dict[capacitance]
                if self.is_grounded:
                    C_mat[branch.nodes[0].id, branch.nodes[1].id] += -1 / (
                        capacitance * 8
                    )
                else:
                    C_mat[branch.nodes[0].id - 1, branch.nodes[1].id - 1] += -1 / (
                        capacitance * 8
                    )

        if not self.is_any_branch_parameter_symbolic() or substitute_params:
            C_mat = C_mat + C_mat.T - np.diag(C_mat.diagonal())
        else:
            C_mat = C_mat + C_mat.T - sympy.diag(*C_mat.diagonal())

        for i in range(C_mat.shape[0]):  # filling the diagonal entries
            C_mat[i, i] = -np.sum(C_mat[i, :])

        if self.is_grounded:  # if grounded remove the 0th column and row from C_mat
            C_mat = C_mat[1:, 1:]
        return C_mat

    def _capacitor_terms(self):
        terms = 0
        branches_with_capacitance = [
            branch
            for branch in self.branches
            if branch.type == "C" or branch.type == "JJ" or branch.type == "JJ2"
        ]
        for c_branch in branches_with_capacitance:
            element_param = {"C": "EC", "JJ": "ECJ", "JJ2": "ECJ"}

            if c_branch.nodes[1].id == 0:
                terms += (
                    1
                    / (16 * c_branch.parameters[element_param[c_branch.type]])
                    * (symbols("vφ" + str(c_branch.nodes[0].id))) ** 2
                )
            elif c_branch.nodes[0].id == 0:
                terms += (
                    1
                    / (16 * c_branch.parameters[element_param[c_branch.type]])
                    * (-symbols("vφ" + str(c_branch.nodes[1].id))) ** 2
                )
            else:
                terms += (
                    1
                    / (16 * c_branch.parameters[element_param[c_branch.type]])
                    * (
                        symbols("vφ" + str(c_branch.nodes[1].id))
                        - symbols("vφ" + str(c_branch.nodes[0].id))
                    )
                    ** 2
                )
        return terms

    def _inductor_terms(self):
        terms = 0
        for l_branch in [branch for branch in self.branches if branch.type == "L"]:
            # adding external flux
            phi_ext = 0
            if l_branch in self.closure_branches:
                index = self.closure_branches.index(l_branch)
                phi_ext += self.external_fluxes[index]

            if l_branch.nodes[0].id == 0:
                terms += (
                    0.5
                    * l_branch.parameters["EL"]
                    * (symbols("φ" + str(l_branch.nodes[1].id)) + phi_ext) ** 2
                )
            elif l_branch.nodes[1].id == 0:
                terms += (
                    0.5
                    * l_branch.parameters["EL"]
                    * (-symbols("φ" + str(l_branch.nodes[0].id)) + phi_ext) ** 2
                )
            else:
                terms += (
                    0.5
                    * l_branch.parameters["EL"]
                    * (
                        symbols("φ" + str(l_branch.nodes[1].id))
                        - symbols("φ" + str(l_branch.nodes[0].id))
                        + phi_ext
                    )
                    ** 2
                )
        return terms

    def _spanning_tree(self):
        r"""
        returns a spanning tree for the given instance
        """

        # making a deep copy to make sure that the original instance is unaffected
        circ_copy = SymbolicCircuit.from_yaml(
            self.input_string, is_file=False, initiate_sym_calc=False
        )

        # **************** removing all the capacitive branches and updating the nodes *
        # identifying capacitive branches
        capacitor_branches = [
            branch for branch in list(circ_copy.branches) if branch.type == "C"
        ]
        for c_branch in capacitor_branches:
            for (
                node
            ) in (
                c_branch.nodes
            ):  # updating the branches attribute for each node that this branch
                # connects
                node.branches = [b for b in node.branches if b is not c_branch]
            circ_copy.branches.remove(c_branch)  # removing the branch

        num_float_nodes = 1
        while num_float_nodes > 0:  # breaks when no floating nodes are detected
            num_float_nodes = 0  # setting
            for node in circ_copy.nodes:
                if len(node.branches) == 0:
                    circ_copy.nodes.remove(node)
                    num_float_nodes += 1
                    continue
                if len(node.branches) == 1:
                    branches_connected_to_node = node.branches[0]
                    circ_copy.branches.remove(branches_connected_to_node)
                    for new_node in branches_connected_to_node.nodes:
                        if new_node != node:
                            new_node.branches = [
                                i
                                for i in new_node.branches
                                if i is not branches_connected_to_node
                            ]
                            num_float_nodes += 1
                            continue
                        else:
                            circ_copy.nodes.remove(node)

        if circ_copy.nodes == []:
            return [], []
        # *****************************************************************************

        # **************** Constructing the node_sets ***************
        if circ_copy.is_grounded:
            node_sets = [[circ_copy.ground_node]]
        else:
            node_sets = [
                [circ_copy.nodes[0]]
            ]  # starting with the first set that has the first node as the only element

        num_nodes = len(circ_copy.nodes)
        # this needs to be done as the ground node is not included in self.nodes
        if circ_copy.is_grounded:
            num_nodes += 1

        # finding all the sets of nodes and filling node_sets
        node_set_index = 0
        while (
            len(sum(node_sets, []))
            < num_nodes  # checking to see if all the nodes are present in node_sets
        ):
            node_set = []

            # code to handle two different capacitive islands in the circuit.
            if node_sets[node_set_index] == []:
                for node in circ_copy.nodes:
                    if node not in [q for p in node_sets for q in p]:
                        node_sets[node_set_index].append(node)
                        break

            for node in node_sets[node_set_index]:
                node_set += node.connected_nodes("all")

            node_set = [
                x
                for x in list(set(node_set))
                if x not in [q for p in node_sets[: node_set_index + 1] for q in p]
            ]
            if node_set:
                node_set.sort(key=lambda x: x.id)

            node_sets.append(node_set)
            node_set_index += 1
        # ***************************

        # **************** constructing the spanning tree ##########
        tree_copy = []  # tree having branches of the instance that is copied

        def connecting_branches(n1: Node, n2: Node):
            return [branch for branch in n1.branches if branch in n2.branches]

        # find the branch connecting this node to another node in a previous node set.
        for index, node_set in enumerate(node_sets):
            if index == 0:
                continue
            for node in node_set:
                for prev_node in node_sets[index - 1]:
                    if len(connecting_branches(node, prev_node)) != 0:
                        tree_copy.append(connecting_branches(node, prev_node)[0])
                        break

        ############## selecting the appropriate branches from circ as from circ_copy #
        def is_same_branch(branch_1: Branch, branch_2: Branch):
            branch_1_dict = branch_1.__dict__
            branch_2_dict = branch_2.__dict__
            if (
                branch_1_dict["type"] == branch_2_dict["type"]
                and branch_1_dict["parameters"] == branch_2_dict["parameters"]
            ):
                if [i.id for i in branch_1_dict["nodes"]] == [
                    i.id for i in branch_2_dict["nodes"]
                ]:
                    return True
                else:
                    return False
            else:
                return False

        tree = []  # tree having branches of the current instance
        for c_branch in tree_copy:
            tree += [b for b in self.branches if is_same_branch(c_branch, b)]

        superconducting_loop_branches = []
        for branch_copy in circ_copy.branches:
            for branch in self.branches:
                if is_same_branch(branch, branch_copy):
                    superconducting_loop_branches.append(branch)

        return tree, superconducting_loop_branches

    def _closure_branches(self):
        r"""
        Returns and stores the closure branches in the circuit.
        """
        tree, superconducting_loop_branches = self._spanning_tree()
        if tree == []:
            closure_branches = []
        else:
            closure_branches = list(set(superconducting_loop_branches) - set(tree))
        return closure_branches

    def _set_external_fluxes(self, closure_branches: List[Branch] = None):
        # setting the class properties

        closure_branches = closure_branches or self._closure_branches()
        closure_branches = [branch for branch in closure_branches if branch.type != "C"]

        if len(closure_branches) > 0:
            self.closure_branches = closure_branches
            self.external_fluxes = [
                symbols("Φ" + str(i + 1)) for i in range(len(closure_branches))
            ]

    def _set_offset_charges(self):
        """
        Create the offset charge variables and store in class attribute offset_charges
        """
        self.offset_charges = []
        for p in self.var_categories["periodic"]:
            self.offset_charges = self.offset_charges + [symbols("ng_" + str(p))]

    def generate_symbolic_lagrangian(
        self,
    ) -> Tuple[sympy.Expr, sympy.Expr, sympy.Expr,]:
        r"""
        Returns three symbolic expressions: lagrangian_θ, potential_θ, lagrangian_φ
        where θ represents the set of new variables and φ represents the set of node
        variables
        """
        transformation_matrix = (
            self.transformation_matrix
        )  # .astype(int) allowing for fractional transformations needs revamp in
        # circuit.py hamiltonian_function

        # defining the φ variables
        φ_dot_vars = [symbols("vφ" + str(i)) for i in range(1, len(self.nodes) + 1)]

        # defining the θ variables
        θ_vars = [symbols("θ" + str(i)) for i in range(1, len(self.nodes) + 1)]
        # defining the θ dot variables
        θ_dot_vars = [symbols("vθ" + str(i)) for i in range(1, len(self.nodes) + 1)]
        # writing φ in terms of θ variables
        φ_vars_θ = transformation_matrix.dot(θ_vars)
        # writing φ dot vars in terms of θ variables
        φ_dot_vars_θ = transformation_matrix.dot(θ_dot_vars)

        # C_terms = self._C_terms()
        C_mat = self._capacitance_matrix()
        if not self.is_any_branch_parameter_symbolic():
            # in terms of node variables
            C_terms_φ = C_mat.dot(φ_dot_vars).dot(φ_dot_vars) * 0.5
            # in terms of new variables
            C_terms_θ = C_mat.dot(φ_dot_vars_θ).dot(φ_dot_vars_θ) * 0.5
        else:
            C_terms_φ = (sympy.Matrix(φ_dot_vars).T * C_mat * sympy.Matrix(φ_dot_vars))[
                0
            ] * 0.5  # in terms of node variables
            C_terms_θ = (
                sympy.Matrix(φ_dot_vars_θ).T * C_mat * sympy.Matrix(φ_dot_vars_θ)
            )[
                0
            ] * 0.5  # in terms of new variables

        inductor_terms_φ = self._inductor_terms()

        JJ_terms_φ = self._junction_terms() + self._JJ2_terms()

        lagrangian_φ = C_terms_φ - inductor_terms_φ - JJ_terms_φ

        potential_φ = inductor_terms_φ + JJ_terms_φ
        potential_θ = (
            potential_φ.copy()
        )  # copying the potential in terms of the old variables to make substitutions

        for index in range(len(self.nodes)):  # converting potential to new variables
            potential_θ = potential_θ.subs(
                symbols("φ" + str(index + 1)), φ_vars_θ[index]
            )

        # eliminating the frozen variables
        for frozen_var_index in self.var_categories["frozen"]:
            sub = sympy.solve(
                potential_θ.diff(symbols("θ" + str(frozen_var_index))),
                symbols("θ" + str(frozen_var_index)),
            )
            potential_θ = potential_θ.replace(
                symbols("θ" + str(frozen_var_index)), sub[0]
            )

        lagrangian_θ = C_terms_θ - potential_θ

        return lagrangian_θ, potential_θ, lagrangian_φ

    def generate_symbolic_hamiltonian(self, substitute_params=False) -> sympy.Expr:
        r"""
        Returns the Hamiltonian of the circuit in terms of the new variables
        :math:`\theta_i`.

        Parameters
        ----------
        substitute_params:
            When set to True, the symbols defined for branch parameters will be
            substituted with the numerical values in the respective Circuit attributes.
        """

        transformation_matrix = self.transformation_matrix
        # basis_inv = np.linalg.inv(basis)[0 : N - n, 0 : N - n]

        # Excluding the frozen modes based on how they are organized in the method
        # variable_transformation_matrix
        if self.is_grounded:
            num_frozen_modes = len(self.var_categories["frozen"])
        else:
            num_frozen_modes = len(self.var_categories["frozen"]) + 1
        num_nodes = len(self.nodes)

        # generating the C_mat_θ by inverting the capacitance matrix
        if self.is_any_branch_parameter_symbolic() and not substitute_params:
            C_mat_θ = (
                transformation_matrix.T
                * self._capacitance_matrix()
                * transformation_matrix
            )[
                0 : num_nodes - num_frozen_modes,
                0 : num_nodes - num_frozen_modes,
            ].inv()  # excluding the frozen modes
        else:
            C_mat_θ = np.linalg.inv(
                (
                    transformation_matrix.T
                    @ self._capacitance_matrix(substitute_params=substitute_params)
                    @ transformation_matrix
                )[
                    0 : num_nodes - num_frozen_modes,
                    0 : num_nodes - num_frozen_modes,
                ]
            )  # excluding the frozen modes

        p_θ_vars = [
            symbols("Q" + str(i)) if i not in self.var_categories["cyclic"]
            # replacing the cyclic charge with 0, as it would not affect the circuit
            # Lagrangian.
            else 0
            for i in range(1, len(self.nodes) + 1 - num_frozen_modes)
        ]  # defining the momentum variables

        # generating the kinetic energy terms for the Hamiltonian
        if not self.is_any_branch_parameter_symbolic():
            C_terms_new = (
                C_mat_θ.dot(p_θ_vars).dot(p_θ_vars) * 0.5
            )  # in terms of new variables
        else:
            C_terms_new = (sympy.Matrix(p_θ_vars).T * C_mat_θ * sympy.Matrix(p_θ_vars))[
                0
            ] * 0.5  # in terms of new variables

        hamiltonian_symbolic = C_terms_new + self.potential_symbolic

        # adding the offset charge variables
        for var_index in self.var_categories["periodic"]:
            hamiltonian_symbolic = hamiltonian_symbolic.subs(
                symbols("Q" + str(var_index)),
                symbols("n" + str(var_index)) + symbols("ng_" + str(var_index)),
            )

        return hamiltonian_symbolic
