""" pint_matrix module defines the pint matrix base class, the design matrix .
and the covariance matrix
"""

import numpy as np
from itertools import combinations
import astropy.units as u
from collections import OrderedDict
import copy


__all__ = [
    "PintMatrix",
    "DesignMatrix",
    "CovarianceMatrix",
    "combine_design_matrices_by_quantity",
    "combine_design_matrices_by_param",
]


class PintMatrix:
    """ PINT matrix is a base class for PINT fitters matrix.

    Parameters
    ----------
    data: `numpy.ndarray`
        Matrix data.
    axis_labels: list of dictionary
        The labels of the axises. Each list element contains the names and
        indices of the labels for the dimension.
        [{dim0_label0: (start, end, unit), dim0_label1:(start, end, unit)},
         {dim1_label0:...}]
        The start and end follows the python slice convention (i.e.,
        end = size + 1).

    Note
    ----
    TODO: 1. add index to label mapping
    """

    def __init__(self, matrix, axis_labels):
        self.matrix = matrix
        self.axis_labels = axis_labels
        # Check dimensions
        if len(axis_labels) != self.matrix.ndim:
            raise ValueError(
                "Axis label dimension does not match the matrix " "dimension."
            )

        # Check label index overlap TODO: should we allow overlap?
        self._check_index_overlap()

    @property
    def ndim(self):
        return self.matrix.ndim

    @property
    def shape(self):
        return self.matrix.shape

    @property
    def labels(self):
        labels = []
        for dim in range(len(self.axis_labels)):
            labels.append(self.get_axis_labels(dim))
        return labels

    @property
    def label_units(self):
        units = []
        for dim in range(len(self.axis_labels)):
            units.append(self.get_axis_labels(dim))
        return units

    def get_label_size(self, label):
        """ Get the size of the a label in each axises.

        Parameter
        ---------
        label: str
            Name of the label.
        """
        lb_sizes = []
        lbs = self.get_label(label)
        for ii, lb in enumerate(lbs):
            size = lb[3] - lb[2]
            lb_sizes.append((ii, size))
        return lb_sizes

    def _check_index_overlap(self):
        for ii in range(self.ndim):
            axis_labels = self.get_axis_labels(ii)
            comb = combinations(axis_labels, 2)
            for cb in comb:
                if cb[0][1][0] <= cb[1][1][1] and cb[1][1][0] <= cb[0][1][1] - 1:
                    raise ValueError("Label index in dim {} has" " overlap".format(ii))

    def _get_label_start(self, label_entry):
        return label_entry[1][0]

    def get_axis_labels(self, axis):
        dim_label = list(self.axis_labels[axis].items())
        dim_label.sort(key=self._get_label_start)
        return dim_label

    def get_label(self, label):
        """ Get the label entry and its dimension. We assume the labels are
        unique in the matrix.
        """
        all_label = []
        for ii, dim in enumerate(self.axis_labels):
            if label in dim.keys():
                all_label.append((label, ii) + dim[label])
        if all_label == []:
            raise KeyError("Label {} is not in the matrix".format(label))
        else:
            return all_label

    def get_label_along_axis(self, axis, label_name):
        """
        Get the request label from on axis.
        """
        label_in_one_axis = self.axis_labels[axis]
        if label_name in label_in_one_axis.keys():
            return (label_name, axis) + label_in_one_axis[label_name]
        else:
            raise ValueError(
                "Label '{}' is not in the axis {}".format(label_name, axis)
            )

    def get_label_slice(self, labels):
        """ Return the given label slices.
        """
        dim_slices = dict([(d, slice(None)) for d in range(self.ndim)])
        new_labels = dict([(d, {}) for d in range(self.ndim)])
        for lb in labels:
            label_info = self.get_label(lb)
            label_size = label_info[2][1] - label_info[2][0]
            # if slice is a list, there is a label already added.
            if isinstance(dim_slices[label_info[0]], list):
                # The start of the new matrix.
                start = len(dim_slices[label_info[0]]) + 1
                dim_slices[label_info[0]] += range(label_info[2][0], label_info[2][1])

            else:
                start = 0
                dim_slices[label_info[0]] = range(label_info[2][0], label_info[2][1])

            new_labels[label_info[0]].update({lb: (start, start + label_size)})
        return list(dim_slices.values()), list(new_labels.values())

    def get_label_matrix(self, labels):
        """ Get a sub-matrix data according to the given labels.
        """
        slice, new_labels = self.get_label_slice(labels)
        return PintMatrix(self.matrix[slice], new_labels)

    def match_labels_along_axis(self, pint_matrix, axis):
        """ Match one axis' labels index between the current matrix and input
        pint matrix. The labels will be matched along axises, not cross the
        axises.

        Parametere
        ----------
        pint_matrix: `PintMatrix` object or its sub-classes.
            The input pint matrix for label matching.
        axis: int
            The matching axis.

        Return
        ------
            Index map between the current labels and input matrix labels along
            axis.
        """
        current_labels = self.get_axis_labels(axis)
        input_labels = pint_matrix.get_axis_labels(axis)
        curr_label_name = [cl[0] for cl in current_labels]
        input_label_name = [il[0] for il in input_labels]
        matched = list(set(curr_label_name).intersection(set(input_label_name)))
        match_index = {}
        for lb in matched:
            l1, ax1, idx1 = self.get_label(lb)
            l2, ax2, idx2 = pint_matrix.get_label(lb)
            match_index[lb] = [idx1, idx2]
        return match_index

    def map_labels(self):
        raise NotImplementedError()

    def append_along_axis(self, pint_matrix, axis):
        """ Append one pint matrix on a given axis.
        """
        raise NotImplementedError()


class DesignMatrix(PintMatrix):
    """ A generic design matrix class for least square fitting.

    Parameters
    ----------
    matrix: `numpy.ndarray`
        Design matrix values.
    axis_labels: list of dictionary
        The labels of the axises. Each list element contains the names and
        indices of the labels for the dimension.
        [{dim0_label0: (start, end, unit), dim0_label1:(start, end, unit)},
         {dim1_label0:...}]
        The start and end follows the python slice convention (i.e.,
        end = size + 1).

    Note
    ----
    Design matrix dim1 is the derivative quantities.
    Design matrix dim2 is the derivative parameters.
    TODO: 1. add index to unit mapping.

    """

    def __init__(self, matrix, labels):
        super(DesignMatrix, self).__init__(matrix, labels)
        self.scaled_by_F0 = False

    @property
    def param_units(self):
        param_lb = self.get_axis_labels(1)
        return [lb[1][2] for lb in param_lb]

    @property
    def derivative_quantity(self):
        param_lb = self.get_axis_labels(0)
        return [lb[0] for lb in param_lb]

    @property
    def derivative_params(self):
        param_lb = self.get_axis_labels(1)
        return [lb[0] for lb in param_lb]


class DesignMatrixMaker:
    """ Class for pint design matrix maker class.

    Parameters
    ----------
    derivative_quantity: str
        The differentiated quantity name. It will be used to search for the
        derivative functions. For instance, if derivative_quantity = 'phase',
        it will search for the 'd_phase_d_param' function in the model.
    quantity_unit: `astropy.units.unit` object
        The unit of the derivative quantity.
    """

    def __new__(cls, derivative_quantity, quantity_unit):
        target_cls = design_matrix_maker_map.get(derivative_quantity.lower(), None)
        # If there is no matching maker, use the current one.
        if target_cls is not None:
            cls = target_cls
        return super().__new__(cls)

    def __init__(self, derivative_quantity, quantity_unit):
        self.derivative_quantity = derivative_quantity
        self.quantity_unit = quantity_unit
        # The derivative function should be a wrapper function like d_phase_d_param()
        self.deriv_func_name = "d_{}_d_param".format(self.derivative_quantity)

    def __call__(
        self, data, model, derivative_params, offset=False, offset_padding=0.0
    ):
        """ A general method to make design matrix.

        Parameters
        ----------
        data: `pint.toa.TOAs` object or other data object
            The data point where the derivatives are evaluated.
        model: `pint.models.TimingModel` object
            The model that provides the derivatives.
        derivative_params: list
            The parameter list for the derivatives 'd_quantity_d_param'.
        offset: bool, optional
            Add the an offset to the beginning of design matrix. Default is False.
            This is match the current phase offset in the design matrix.
        offset_padding: float, optional
            if including offset, the value for padding.
        """
        # Get derivative functions
        deriv_func = getattr(model, self.deriv_func_name)
        # Check if the derivate quantity a phase derivative
        params = ["Offset"] if offset else []
        params += derivative_params
        labels = []
        M = np.zeros((len(data), len(params)))
        labels.append({self.derivative_quantity: (0, M.shape[0], self.quantity_unit)})
        labels_dim2 = {}
        for ii, param in enumerate(params):
            if param == "Offset":
                M[:, ii] = offset_padding
                param_unit = u.Unit("")
            else:
                param_unit = getattr(model, param).units
                q = deriv_func(data, param).to(self.quantity_unit / param_unit)
                # This will strip the units
                M[:, ii] = q
            labels_dim2[param] = (ii, ii + 1, param_unit)

        labels.append(labels_dim2)
        return DesignMatrix(M, labels)


class PhaseDesignMatrixMaker(DesignMatrixMaker):
    """ A specific class for makeing phase design matrix.
    """

    def __call__(
        self,
        data,
        model,
        derivative_params,
        scaled_by_F0=True,
        offset=True,
        offset_padding=1.0,
    ):
        """ Create the phase design matrix.

        Parameters
        ----------
        data: `pint.toa.TOAs` object or other data object
            The data point where the derivatives are evaluated.
        model: `pint.models.TimingModel` object
            The model that provides the derivatives.
        derivative_params: list
            The parameter list for the derivatives 'd_quantity_d_param'.
        scale_by_F0: bool, optional
            Flag for scaling the matrxi by spin rate. Default is True
        offset: bool, optional
            Add the an offset to the beginning of design matrix. Default is True.
        offset_padding: float, optional
            if including offset, the value for padding. Default is 1.0
        """
        deriv_func = getattr(model, self.deriv_func_name)
        # Check if the derivate quantity a phase derivative
        params = ["Offset"] if offset else []
        params += derivative_params
        labels = []
        M = np.zeros((data.ntoas, len(params)))
        labels.append({self.derivative_quantity: (0, M.shape[0], self.quantity_unit)})
        labels_dim2 = {}
        delay = model.delay(data)
        for ii, param in enumerate(params):
            if param == "Offset":
                M[:, ii] = offset_padding
                param_unit = u.Unit("")
            else:
                param_unit = getattr(model, param).units
                # Since this is the phase derivative, we know the quantity unit.
                q = deriv_func(data, delay, param).to(u.Unit("") / param_unit)

                # NOTE Here we have negative sign here. Since in pulsar timing
                # the residuals are calculated as (Phase - int(Phase)), which is different
                # from the conventional definition of least square definition (Data - model)
                # We decide to add minus sign here in the design matrix, so the fitter
                # keeps the conventional way.
                M[:, ii] = -q
            labels_dim2[param] = (ii, ii + 1, param_unit)

        labels.append(labels_dim2)

        if scaled_by_F0:
            mask = []
            for ii, param in enumerate(params):
                if param == "Offset":
                    continue
                mask.append(ii)
            M[:, mask] /= model.F0.value
            # TODO maybe use defined label is better
            labels[0] = {
                self.derivative_quantity: (0, M.shape[0], self.quantity_unit * u.s)
            }
        d_matrix = DesignMatrix(M, labels)
        d_matrix.scaled_by_F0 = scaled_by_F0
        return d_matrix


class TOADesignMatrixMaker(PhaseDesignMatrixMaker):
    """ A simple design matrix maker subclassed from the PhaseDesignMatrixMaker.
    It changes the derivative quantity from phase to TOAs.
    """

    def __init__(self, derivative_quantity, quantity_unit):
        self.derivative_quantity = derivative_quantity
        self.quantity_unit = quantity_unit
        # The derivative function should be a wrapper function like d_phase_d_param()
        self.deriv_func_name = "d_phase_d_param"

    def __call__(self, data, model, derivative_params, offset=True, offset_padding=1.0):
        d_matrix = super().__call__(
            data, model, derivative_params, offset=offset, offset_padding=offset_padding
        )
        return d_matrix


class NoiseDesignMatrixMaker(DesignMatrixMaker):
    """ Specific design matrix for noise model

    Note
    ----
    TODO: give proper labels.
    """

    def __call__(self, data, model):
        result = []
        if len(model.basis_funcs) == 0:
            return None

        for nf in model.basis_funcs:
            result.append(nf(data)[0])
        M = np.hstack([r for r in result])
        labels = [
            {"toa": (0, M.shape[0], u.s)},
            {"toa_noise_params": (0, M.shape[1], u.s)},
        ]
        return DesignMatrix(M, labels)


design_matrix_maker_map = {
    "phase": PhaseDesignMatrixMaker,
    "toa": TOADesignMatrixMaker,
    "toa_noise": NoiseDesignMatrixMaker,
}


def combine_design_matrices_by_quantity(design_matrices):
    """ A fast method to combine two design matrix along the derivative
    quantity. If requires the parameter list match to each other.

    Parameter
    ---------
    design_matrices: `pint_matrix.DesignMatrix` object
        The input design matrix.

    """
    axis_labels = [{}, design_matrices[0].axis_labels[1]]
    all_matrix = []
    for ii, d_matrix in enumerate(design_matrices):
        if d_matrix.derivative_params != design_matrices[0].derivative_params:
            raise ValueError(
                "Input design matrix's derivative parameters do "
                "not match the current derivative parameters."
            )
        # only update the derivative quantity label.
        if ii == 0:
            axis_labels[0].update(d_matrix.axis_labels[0])
            # Set the start index of next label, which is the current ending index
            offset = d_matrix.get_axis_labels(0)[-1][1][1]
        else:
            new_labels = []
            old_labels = d_matrix.get_axis_labels(0)
            for olb in old_labels:
                # apply offset to the next label.
                new_labels.append(
                    (olb[0], (olb[1][0] + offset, olb[1][1] + offset, olb[1][2]))
                )
                off_set = new_labels[-1][1][1]
            axis_labels[0].update(dict(new_labels))
        all_matrix.append(d_matrix.matrix)
    result = DesignMatrix(np.vstack(all_matrix), axis_labels)
    return result


def combine_design_matrices_by_param(matrix1, matrix2, padding=0.0):
    """ A fast method to combine two design matrix along the param axis.

    Parameter
    ---------
    matrix1: `pint_matrix.DesignMatrix` object
        The input design matrices.
    matrix2: `pint_matrix.DesignMatrix` object
        The input design matrices.
    padding: float, optional
        The padding number if the derivative quantity is independent from the
        parameters. Default is 0.0.
    """
    # init the quantity axis.
    axis_labels = copy.deepcopy(matrix1.axis_labels)

    # Get the base matrix labels and indcies.
    base_params = matrix1.derivative_params
    base_quantity_index = matrix1.axis_labels[0]

    # Check if the parameters has overlap.
    for d_param in matrix2.derivative_params:
        if d_param in base_params:
            raise ValueError(
                "Input design matrix {} has duplicated "
                " parameters with matrix {}".format(ii, 0)
            )
    # check if input design matrix has same quantity and padding.
    new_quantity_index = {}
    append_offset = matrix1.shape[0]
    base_matrix = matrix1.matrix
    for d_quantity in matrix2.derivative_quantity:
        quantity_label = matrix2.get_label_along_axis(0, d_quantity)
        if d_quantity in base_quantity_index.keys():
            # Check quantity size
            d_quantity_size = quantity_label[3] - quantity_label[2]
            base_size = (
                base_quantity_index[d_quantity][1] - base_quantity_index[d_quantity][0]
            )

            if d_quantity_size != base_size:
                raise ValueError(
                    "Input design matrix's label "
                    "{} has different size with matrix"
                    " {}".format(d_quantity, 0)
                )
            else:
                # assign new index for combined matrix
                new_quantity_index[d_quantity] = (
                    base_quantity_index[d_quantity][0],
                    base_quantity_index[d_quantity][1],
                )

        else:
            # if quantity is not in the base matrix, append to the base matrix
            append_size = matrix2.get_label_size(d_quantity)[0][1]
            new_quantity_index[d_quantity] = (
                append_offset,
                append_offset + append_size,
            )
            append_offset += append_size
            append_data = np.zeros((append_size, matrix2.shape[1]))
            append_data.fill(padding)
            base_matrix = np.vstack((base_matrix, append_data))

        axis_labels[0].update(
            {d_quantity: new_quantity_index[d_quantity] + (quantity_label[2],)}
        )

    # Combine matrix
    # make default new matrix with the rigth size
    new_matrix = np.zeros((base_matrix.shape[0], matrix2.shape[1]))
    new_matrix.fill(padding)
    # Fill up the new_matrix with matrix2
    for quantity, new_idx in new_quantity_index.items():
        old_idx = matrix2.get_label_along_axis(0, d_quantity)[2:4]
        new_matrix[new_idx[0] : new_idx[1], :] = matrix2.matrix[
            old_idx[0] : old_idx[1], :
        ]

    new_param_label = []
    param_offset = matrix1.shape[1]
    for lb, lb_index in matrix2.axis_labels[1].items():  # change parameter index
        new_param_label.append(
            (lb, (lb_index[0] + param_offset, lb_index[1] + param_offset, lb_index[2]))
        )
        param_offset += lb_index[1] - lb_index[0]

    axis_labels[1].update(dict(new_param_label))
    # append the new matrix
    result = np.hstack([base_matrix, new_matrix])
    return DesignMatrix(result, axis_labels)


class CovarianceMatrix(PintMatrix):
    """ A class for symmetric covariance matrix.
    """

    def __init__(self, matrix, labels):
        # Check if the covariance matrix is symmetric.
        if matrix.shape[0] != matrix.shape[1]:
            raise ValueError("The input matrix is not symmetric.")
        # Check if the labels are symmetric
        if len(labels[0]) != len(labels[1]):
            raise ValueError("The input labels are not sysmmetric.")
        super(CovarianceMatrix, self).__init__(matrix, labels)


class CovarianceMatrixMaker:
    """ Class for pint design matrix maker class.

    Parameters
    ----------
    covariance_quantity: str
        The covariance quantity name. It will be used to search for the
        functions. For instance, if derivative_quantity = 'phase',
        it will search for the 'd_phase_d_param' function in the model.
    quantity_unit: `astropy.units.unit` object
        The unit of the derivative quantity.
    """

    def __init__(self, covariance_quantity, quantity_unit):
        self.covariance_quantity = covariance_quantity
        self.quantity_unit = quantity_unit
        # The derivative function should be a wrapper function like d_phase_d_param()
        self.cov_func_name = "{}_covariance_matrix".format(self.covariance_quantity)

    def __call__(self, data, model):
        """ A general method to make design matrix.

        Parameters
        ----------
        data: `pint.toa.TOAs` object or other data object
            The data point where the derivatives are evaluated.
        model: `pint.models.TimingModel` object
            The model that provides the derivatives.
        """
        func = getattr(model, self.cov_func_name)
        M = func(data)
        label = [
            {self.covariance_quantity: (0, M.shape[0], self.quantity_unit ** 2)}
        ] * 2
        return CovarianceMatrix(M, label)


def combine_covariance_matrix(covariance_matrices, crossterm={}, crossterm_padding=0.0):
    """ A fast method to combine two covariance matrix diagonaly.

    Parameters
    ----------
    covariance_matrices: list of `CovarianceMatrix` object.
        The design matrices needs to combine.
    crossterm: dictionary, optional
        The padding matrix of the cross area of two type of covariance matrices.
        The input formate is {(label1, label2): numpy.ndarray}. Default is {}.
    crossterm_padding: float
        If the corss term is not give, use the given padding number. Default is
        0.0.
    """
    new_size = 0
    new_label = []
    offset = 0
    for cm in covariance_matrices:
        # Since covariance matrix are symmtric, only use dim1
        new_size += cm.shape[0]
        cm_labels = cm.get_axis_labels(1)
        label_entry = tuple()
        for cmlb in cm_labels:
            label_entry = (
                cmlb[0],
                (offset + cmlb[1][0], offset + cmlb[1][1], cmlb[1][2],),
            )
            new_label.append(label_entry)
        offset += cm.shape[0]

    if crossterm != {}:
        new_cm = np.zeros((new_size, new_size))
    else:
        new_cm = np.empty((new_size, new_size))
        new_cm.fill(crossterm_padding)

    # Assign numbers to the matrix
    for ii, lb1 in enumerate(new_label):
        for jj, lb2 in enumerate(new_label):
            if ii == jj:
                new_cm[
                    lb1[1][0] : lb1[1][1], lb2[1][0] : lb2[1][1]
                ] = covariance_matrices[ii].matrix
            else:
                if crossterm != {}:
                    cross_m = crossterm.get((lb1, lb2), None)
                    if cross_m is None:
                        cross_m = crossterm.get((lb2, lb1), None).T

                    new_cm[lb1[1][0] : lb1[1][1], lb2[1][0] : lb2[1][1]] = cross_m
    return CovarianceMatrix(new_cm, [OrderedDict(new_label),] * 2)
