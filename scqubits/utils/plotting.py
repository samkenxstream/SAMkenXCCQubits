# plotting.py
#
# This file is part of scqubits.
#
#    Copyright (c) 2019, Jens Koch and Peter Groszkowski
#    All rights reserved.
#
#    This source code is licensed under the BSD-style license found in the
#    LICENSE file in the root directory of this source tree.
############################################################################

import warnings
import os

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
from mpl_toolkits.axes_grid1 import make_axes_locatable

import scqubits.core.constants as constants
import scqubits.utils.plot_defaults as defaults
from scqubits.settings import DEFAULT_ENERGY_UNITS
from scqubits.utils.misc import process_which


try:
    from labellines import labelLines
    _LABELLINES_ENABLED = True
except ImportError:
    _LABELLINES_ENABLED = False


def _process_options(figure, axes, opts=None, **kwargs):
    """
    Processes plotting options.

    Parameters
    ----------
    figure: matplotlib.Figure
    axes: matplotlib.Axes
    opts: dict
        keyword dictionary with custom options
    **kwargs: dict
        standard plotting option (see separate documentation)
    """
    if opts is None:
        option_dict = kwargs
    else:
        option_dict = {**opts, **kwargs}

    for key, value in option_dict.items():
        if key not in defaults.SPECIAL_PLOT_OPTIONS:
            set_method = getattr(axes, 'set_' + key)
            set_method(value)
        elif key == 'x_range':
            warnings.warn('x_range is deprecated, use xlim instead', FutureWarning)
            axes.set_xlim(value)
        elif key == 'y_range':
            warnings.warn('y_range is deprecated, use ylim instead', FutureWarning)
            axes.set_ylim(value)
        elif key == 'ymax':
            ymax = value
            ymin, _ = axes.get_ylim()
            ymin = ymin - (ymax - ymin) * 0.05
            axes.set_ylim(ymin, ymax)
        elif key == 'figsize':
            figure.set_size_inches(value)

    filename = kwargs.get('filename')
    if filename:
        figure.savefig(os.path.splitext(filename)[0] + '.pdf')


def wavefunction1d(wavefunc, potential_vals=None, offset=0, scaling=1, **kwargs):
    """
    Plots the amplitude of a single real-valued 1d wave function, along with the potential energy if provided.

    Parameters
    ----------
    wavefunc: WaveFunction object
        basis and amplitude data of wave function to be plotted
    potential_vals: array of float
        potential energies, array length must match basis array of `wavefunc`
    offset: float
        y-offset for the wave function (e.g., shift by eigenenergy)
    scaling: float, optional
        scaling factor for wave function amplitudes
    **kwargs: dict
        standard plotting option (see separate documentation)

    Returns
    -------
    tuple(Figure, Axes)
        matplotlib objects for further editing
    """
    fig, axes = kwargs.get('fig_ax') or plt.subplots()

    x_vals = wavefunc.basis_labels
    y_vals = offset + scaling * wavefunc.amplitudes
    offset_vals = [offset] * len(x_vals)

    if potential_vals is not None:
        axes.plot(x_vals, potential_vals, color='gray')

    axes.plot(x_vals, y_vals)
    axes.fill_between(x_vals, y_vals, offset_vals, where=(y_vals != offset_vals), interpolate=True)
    _process_options(fig, axes, opts=defaults.wavefunction1d(), **kwargs)
    return fig, axes


def wavefunction1d_discrete(wavefunc, **kwargs):
    """
    Plots the amplitude of a real-valued 1d wave function in a discrete basis. (Example: transmon in the charge basis.)

    Parameters
    ----------
    wavefunc: WaveFunction object
        basis and amplitude data of wave function to be plotted
    **kwargs: dict
        standard plotting option (see separate documentation)

    Returns
    -------
    tuple(Figure, Axes)
        matplotlib objects for further editing
    """
    fig, axes = kwargs.get('fig_ax') or plt.subplots()

    x_vals = wavefunc.basis_labels
    width = .75

    axes.bar(x_vals, wavefunc.amplitudes, width=width)
    axes.set_xticks(x_vals)
    axes.set_xticklabels(x_vals)
    _process_options(fig, axes, defaults.wavefunction1d_discrete(), **kwargs)

    return fig, axes


def wavefunction2d(wavefunc, zero_calibrate=False, **kwargs):
    """
    Creates a density plot of the amplitude of a real-valued wave function in 2 "spatial" dimensions.

    Parameters
    ----------
    wavefunc: WaveFunctionOnGrid object
        basis and amplitude data of wave function to be plotted
    zero_calibrate: bool, optional
        whether to calibrate plot to zero amplitude
    **kwargs: dict
        standard plotting option (see separate documentation)

    Returns
    -------
    tuple(Figure, Axes)
        matplotlib objects for further editing
    """
    fig, axes = kwargs.get('fig_ax') or plt.subplots()

    min_vals = wavefunc.gridspec.min_vals
    max_vals = wavefunc.gridspec.max_vals

    if zero_calibrate:
        absmax = np.amax(np.abs(wavefunc.amplitudes))
        imshow_minval = -absmax
        imshow_maxval = absmax
        cmap = plt.get_cmap('PRGn')
    else:
        imshow_minval = np.min(wavefunc.amplitudes)
        imshow_maxval = np.max(wavefunc.amplitudes)
        cmap = plt.cm.viridis

    im = axes.imshow(wavefunc.amplitudes, extent=[min_vals[0], max_vals[0], min_vals[1], max_vals[1]],
                     cmap=cmap, vmin=imshow_minval, vmax=imshow_maxval, origin='lower', aspect='auto')
    divider = make_axes_locatable(axes)
    cax = divider.append_axes("right", size="2%", pad=0.05)
    fig.colorbar(im, cax=cax)

    _process_options(fig, axes, defaults.wavefunction2d(), **kwargs)
    return fig, axes


def contours(x_vals, y_vals, func, contour_vals=None, show_colorbar=True, **kwargs):
    """Contour plot of a 2d function `func(x,y)`.

    Parameters
    ----------
    x_vals: (ordered) list
        x values for the x-y evaluation grid
    y_vals: (ordered) list
        y values for the x-y evaluation grid
    func: function f(x,y)
        function for which contours are to be plotted
    contour_vals: list of float, optional
        contour values can be specified if so desired
    show_colorbar: bool, optional
    **kwargs: dict
        standard plotting option (see separate documentation)

    Returns
    -------
    tuple(Figure, Axes)
        matplotlib objects for further editing
    """
    fig, axes = kwargs.get('fig_ax') or plt.subplots()

    x_grid, y_grid = np.meshgrid(x_vals, y_vals)
    z_array = func(x_grid, y_grid)

    im = axes.contourf(x_grid, y_grid, z_array, levels=contour_vals, cmap=plt.cm.viridis, origin="lower")

    if show_colorbar:
        divider = make_axes_locatable(axes)
        cax = divider.append_axes("right", size="2%", pad=0.05)
        fig.colorbar(im, cax=cax)

    _process_options(fig, axes, opts=defaults.contours(x_vals, y_vals), **kwargs)
    return fig, axes


def matrix(data_matrix, mode='abs', **kwargs):
    """
    Create a "skyscraper" plot and a 2d color-coded plot of a matrix.

    Parameters
    ----------
    data_matrix: ndarray of float or complex
        2d matrix data
    mode: str from `constants.MODE_FUNC_DICT`
        choice of processing function to be applied to data
    **kwargs: dict
        standard plotting option (see separate documentation)

    Returns
    -------
    Figure, (Axes1, Axes2)
        figure and axes objects for further editing
    """
    if 'fig_ax' in kwargs:
        fig, (ax1, ax2) = kwargs['fig_ax']
    else:
        fig = plt.figure()
        ax1 = fig.add_subplot(1, 2, 1, projection='3d')
        ax2 = plt.subplot(1, 2, 2)

    matsize = len(data_matrix)
    element_count = matsize ** 2  # num. of elements to plot

    xgrid, ygrid = np.meshgrid(range(matsize), range(matsize))
    xgrid = xgrid.T.flatten() - 0.5  # center bars on integer value of x-axis
    ygrid = ygrid.T.flatten() - 0.5  # center bars on integer value of y-axis

    zbottom = np.zeros(element_count)  # all bars start at z=0
    dx = 0.75 * np.ones(element_count)  # width of bars in x-direction
    dy = dx  # width of bars in y-direction (same as x-direction)

    modefunction = constants.MODE_FUNC_DICT[mode]
    zheight = modefunction(data_matrix).flatten()  # height of bars from matrix elements
    nrm = mpl.colors.Normalize(0, max(zheight))  # <-- normalize colors to max. data
    colors = plt.cm.viridis(nrm(zheight))  # list of colors for each bar

    # skyscraper plot
    ax1.view_init(azim=210, elev=23)
    ax1.bar3d(xgrid, ygrid, zbottom, dx, dy, zheight, color=colors)
    ax1.axes.w_xaxis.set_major_locator(plt.IndexLocator(1, -0.5))  # set x-ticks to integers
    ax1.axes.w_yaxis.set_major_locator(plt.IndexLocator(1, -0.5))  # set y-ticks to integers
    ax1.set_zlim3d([0, max(zheight)])

    # 2d plot
    ax2.matshow(modefunction(data_matrix), cmap=plt.cm.viridis)
    cax, _ = mpl.colorbar.make_axes(ax2, shrink=.75, pad=.02)  # add colorbar with normalized range
    _ = mpl.colorbar.ColorbarBase(cax, cmap=plt.cm.viridis, norm=nrm)

    _process_options(fig, ax1, opts=defaults.matrix(), **kwargs)
    return fig, (ax1, ax2)


def data_vs_paramvals(xdata, ydata, label_list=None, **kwargs):
    """Plot of a set of yadata vs xdata.
    The individual points correspond to the a provided array of parameter values.

    Parameters
    ----------
    xdata, ydata: ndarray
        must have compatible shapes for matplotlib.pyplot.plot
    label_list: list(str), optional
        list of labels associated with the individual curves to be plotted
    **kwargs: dict
        standard plotting option (see separate documentation)

    Returns
    -------
    tuple(Figure, Axes)
        matplotlib objects for further editing
    """
    fig, axes = kwargs.get('fig_ax') or plt.subplots()

    if label_list is None:
        axes.plot(xdata, ydata)
    else:
        for idx, ydataset in enumerate(ydata.T):
            axes.plot(xdata, ydataset, label=label_list[idx])
        axes.legend(loc='center left', bbox_to_anchor=(1, 0.5))
    _process_options(fig, axes, **kwargs)
    return fig, axes


def evals_vs_paramvals(specdata, which=-1, subtract_ground=False, label_list=None, **kwargs):
    """Generates a simple plot of a set of eigenvalues as a function of one parameter.
    The individual points correspond to the a provided array of parameter values.

    Parameters
    ----------
    specdata: SpectrumData
        object includes parameter name, values, and resulting eigenenergies
    which: int or list(int)
        number of desired eigenvalues (sorted from smallest to largest); default: -1, signals all eigenvalues
        or: list of specific eigenvalues to include
    subtract_ground: bool
        whether to subtract the ground state energy
    label_list: list(str), optional
        list of labels associated with the individual curves to be plotted
    **kwargs: dict
        standard plotting option (see separate documentation)

    Returns
    -------
    tuple(Figure, Axes)
        matplotlib objects for further editing
    """
    index_list = process_which(which, specdata.energy_table[0].size)

    xdata = specdata.param_vals
    ydata = specdata.energy_table[:, index_list]
    if subtract_ground:
        ydata = (ydata.T - ydata[:, 0]).T
    return data_vs_paramvals(xdata, ydata, label_list=label_list,
                             **defaults.evals_vs_paramvals(specdata, **kwargs))


def matelem_vs_paramvals(specdata, select_elems=4, mode='abs', **kwargs):
    """Generates a simple plot of matrix elements as a function of one parameter.
    The individual points correspond to the a provided array of parameter values.

    Parameters
    ----------
    specdata: SpectrumData
        object includes parameter name, values, and matrix elements
    select_elems: int or list
        either maximum index of desired matrix elements, or list [(i1, i2), (i3, i4), ...] of index tuples
        for specific desired matrix elements
    mode: str from `constants.MODE_FUNC_DICT`, optional
        choice of processing function to be applied to data (default value = 'abs')
    **kwargs: dict
        standard plotting option (see separate documentation)

    Returns
    -------
    tuple(Figure, Axes)
        matplotlib objects for further editing
    """
    fig, axes = kwargs.get('fig_ax') or plt.subplots()

    x = specdata.param_vals

    modefunction = constants.MODE_FUNC_DICT[mode]
    if isinstance(select_elems, int):
        for row in range(select_elems):
            for col in range(row + 1):
                y = modefunction(specdata.matrixelem_table[:, row, col])
                axes.plot(x, y, label=str(row) + ',' + str(col))
    else:
        for index_pair in select_elems:
            y = modefunction(specdata.matrixelem_table[:, index_pair[0], index_pair[1]])
            axes.plot(x, y, label=str(index_pair[0]) + ',' + str(index_pair[1]))

    if _LABELLINES_ENABLED:
        labelLines(axes.get_lines(), zorder=2.0)
    else:
        axes.legend(loc='center left', bbox_to_anchor=(1, 0.5))
    _process_options(fig, axes, opts=defaults.matelem_vs_paramvals(specdata), **kwargs)
    return fig, axes


def print_matrix(matrix, show_numbers=True, **kwargs):
    """Pretty print a matrix, optionally printing the numerical values of the data.
    """
    fig, axes = kwargs.get('fig_ax') or plt.subplots()

    m = axes.matshow(matrix, cmap=plt.cm.viridis, interpolation='none')
    fig.colorbar(m, ax=axes)

    if show_numbers:
        for y_index in range(matrix.shape[0]):
            for x_index in range(matrix.shape[1]):
                axes.text(x_index, y_index, "{:.03f}".format(matrix[y_index, x_index]),
                          va='center', ha='center', fontsize=8, rotation=45, color='white')
    # shift the grid
    for axis, locs in [(axes.xaxis, np.arange(matrix.shape[1])), (axes.yaxis, np.arange(matrix.shape[0]))]:
        axis.set_ticks(locs + 0.5, minor=True)
        axis.set(ticks=locs, ticklabels=locs)
    axes.grid(True, which='minor')
    axes.grid(False, which='major')

    _process_options(fig, axes, **kwargs)
    return fig, axes
