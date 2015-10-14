from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

from matplotlib.externals import six

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.tri as mtri
from nose.tools import assert_equal, assert_raises, assert_true, assert_false
from numpy.testing import assert_array_equal, assert_array_almost_equal,\
    assert_array_less
import numpy.ma.testutils as matest
from matplotlib.testing.decorators import image_comparison
import matplotlib.cm as cm
from matplotlib.path import Path


def test_delaunay():
    # No duplicate points, regular grid.
    nx = 5
    ny = 4
    x, y = np.meshgrid(np.linspace(0.0, 1.0, nx), np.linspace(0.0, 1.0, ny))
    x = x.ravel()
    y = y.ravel()
    npoints = nx*ny
    ntriangles = 2 * (nx-1) * (ny-1)
    nedges = 3*nx*ny - 2*nx - 2*ny + 1

    # Create delaunay triangulation.
    triang = mtri.Triangulation(x, y)

    # The tests in the remainder of this function should be passed by any
    # triangulation that does not contain duplicate points.

    # Points - floating point.
    assert_array_almost_equal(triang.x, x)
    assert_array_almost_equal(triang.y, y)

    # Triangles - integers.
    assert_equal(len(triang.triangles), ntriangles)
    assert_equal(np.min(triang.triangles), 0)
    assert_equal(np.max(triang.triangles), npoints-1)

    # Edges - integers.
    assert_equal(len(triang.edges), nedges)
    assert_equal(np.min(triang.edges), 0)
    assert_equal(np.max(triang.edges), npoints-1)

    # Neighbors - integers.
    # Check that neighbors calculated by C++ triangulation class are the same
    # as those returned from delaunay routine.
    neighbors = triang.neighbors
    triang._neighbors = None
    assert_array_equal(triang.neighbors, neighbors)

    # Is each point used in at least one triangle?
    assert_array_equal(np.unique(triang.triangles), np.arange(npoints))


def test_delaunay_duplicate_points():
    # x[duplicate] == x[duplicate_of]
    # y[duplicate] == y[duplicate_of]
    npoints = 10
    duplicate = 7
    duplicate_of = 3

    np.random.seed(23)
    x = np.random.random((npoints))
    y = np.random.random((npoints))
    x[duplicate] = x[duplicate_of]
    y[duplicate] = y[duplicate_of]

    # Create delaunay triangulation.
    triang = mtri.Triangulation(x, y)

    # Duplicate points should be ignored, so the index of the duplicate points
    # should not appear in any triangle.
    assert_array_equal(np.unique(triang.triangles),
                       np.delete(np.arange(npoints), duplicate))


def test_delaunay_points_in_line():
    # Cannot triangulate points that are all in a straight line, but check
    # that delaunay code fails gracefully.
    x = np.linspace(0.0, 10.0, 11)
    y = np.linspace(0.0, 10.0, 11)
    assert_raises(RuntimeError, mtri.Triangulation, x, y)

    # Add an extra point not on the line and the triangulation is OK.
    x = np.append(x, 2.0)
    y = np.append(y, 8.0)
    triang = mtri.Triangulation(x, y)


def test_delaunay_insufficient_points():
    # Triangulation should raise a ValueError if passed less than 3 points.
    assert_raises(ValueError, mtri.Triangulation, [], [])
    assert_raises(ValueError, mtri.Triangulation, [1], [5])
    assert_raises(ValueError, mtri.Triangulation, [1, 2], [5, 6])

    # Triangulation should also raise a ValueError if passed duplicate points
    # such that there are less than 3 unique points.
    assert_raises(ValueError, mtri.Triangulation, [1, 2, 1], [5, 6, 5])
    assert_raises(ValueError, mtri.Triangulation, [1, 2, 2], [5, 6, 6])
    assert_raises(ValueError, mtri.Triangulation, [1, 1, 1, 2, 1, 2],
                  [5, 5, 5, 6, 5, 6])


def test_delaunay_robust():
    # Fails when mtri.Triangulation uses matplotlib.delaunay, works when using
    # qhull.
    tri_points = np.array([
        [0.8660254037844384, -0.5000000000000004],
        [0.7577722283113836, -0.5000000000000004],
        [0.6495190528383288, -0.5000000000000003],
        [0.5412658773652739, -0.5000000000000003],
        [0.811898816047911, -0.40625000000000044],
        [0.7036456405748561, -0.4062500000000004],
        [0.5953924651018013, -0.40625000000000033]])
    test_points = np.asarray([
        [0.58, -0.46],
        [0.65, -0.46],
        [0.65, -0.42],
        [0.7, -0.48],
        [0.7, -0.44],
        [0.75, -0.44],
        [0.8, -0.48]])

    # Utility function that indicates if a triangle defined by 3 points
    # (xtri, ytri) contains the test point xy.  Avoid calling with a point that
    # lies on or very near to an edge of the triangle.
    def tri_contains_point(xtri, ytri, xy):
        tri_points = np.vstack((xtri, ytri)).T
        return Path(tri_points).contains_point(xy)

    # Utility function that returns how many triangles of the specified
    # triangulation contain the test point xy.  Avoid calling with a point that
    # lies on or very near to an edge of any triangle in the triangulation.
    def tris_contain_point(triang, xy):
        count = 0
        for tri in triang.triangles:
            if tri_contains_point(triang.x[tri], triang.y[tri], xy):
                count += 1
        return count

    # Using matplotlib.delaunay, an invalid triangulation is created with
    # overlapping triangles; qhull is OK.
    triang = mtri.Triangulation(tri_points[:, 0], tri_points[:, 1])
    for test_point in test_points:
        assert_equal(tris_contain_point(triang, test_point), 1)

    # If ignore the first point of tri_points, matplotlib.delaunay throws a
    # KeyError when calculating the convex hull; qhull is OK.
    triang = mtri.Triangulation(tri_points[1:, 0], tri_points[1:, 1])


@image_comparison(baseline_images=['tripcolor1'], extensions=['png'])
def test_tripcolor():
    x = np.asarray([0, 0.5, 1, 0,   0.5, 1,   0, 0.5, 1, 0.75])
    y = np.asarray([0, 0,   0, 0.5, 0.5, 0.5, 1, 1,   1, 0.75])
    triangles = np.asarray([
        [0, 1, 3], [1, 4, 3],
        [1, 2, 4], [2, 5, 4],
        [3, 4, 6], [4, 7, 6],
        [4, 5, 9], [7, 4, 9], [8, 7, 9], [5, 8, 9]])

    # Triangulation with same number of points and triangles.
    triang = mtri.Triangulation(x, y, triangles)

    Cpoints = x + 0.5*y

    xmid = x[triang.triangles].mean(axis=1)
    ymid = y[triang.triangles].mean(axis=1)
    Cfaces = 0.5*xmid + ymid

    plt.subplot(121)
    plt.tripcolor(triang, Cpoints, edgecolors='k')
    plt.title('point colors')

    plt.subplot(122)
    plt.tripcolor(triang, facecolors=Cfaces, edgecolors='k')
    plt.title('facecolors')


def test_no_modify():
    # Test that Triangulation does not modify triangles array passed to it.
    triangles = np.array([[3, 2, 0], [3, 1, 0]], dtype=np.int32)
    points = np.array([(0, 0), (0, 1.1), (1, 0), (1, 1)])

    old_triangles = triangles.copy()
    tri = mtri.Triangulation(points[:, 0], points[:, 1], triangles)
    edges = tri.edges
    assert_array_equal(old_triangles, triangles)


def test_trifinder():
    # Test points within triangles of masked triangulation.
    x, y = np.meshgrid(np.arange(4), np.arange(4))
    x = x.ravel()
    y = y.ravel()
    triangles = [[0, 1, 4], [1, 5, 4], [1, 2, 5], [2, 6, 5], [2, 3, 6],
                 [3, 7, 6], [4, 5, 8], [5, 9, 8], [5, 6, 9], [6, 10, 9],
                 [6, 7, 10], [7, 11, 10], [8, 9, 12], [9, 13, 12], [9, 10, 13],
                 [10, 14, 13], [10, 11, 14], [11, 15, 14]]
    mask = np.zeros(len(triangles))
    mask[8:10] = 1
    triang = mtri.Triangulation(x, y, triangles, mask)
    trifinder = triang.get_trifinder()

    xs = [0.25, 1.25, 2.25, 3.25]
    ys = [0.25, 1.25, 2.25, 3.25]
    xs, ys = np.meshgrid(xs, ys)
    xs = xs.ravel()
    ys = ys.ravel()
    tris = trifinder(xs, ys)
    assert_array_equal(tris, [0, 2, 4, -1, 6, -1, 10, -1,
                              12, 14, 16, -1, -1, -1, -1, -1])
    tris = trifinder(xs-0.5, ys-0.5)
    assert_array_equal(tris, [-1, -1, -1, -1, -1, 1, 3, 5,
                              -1, 7, -1, 11, -1, 13, 15, 17])

    # Test points exactly on boundary edges of masked triangulation.
    xs = [0.5, 1.5, 2.5, 0.5, 1.5, 2.5, 1.5, 1.5, 0.0, 1.0, 2.0, 3.0]
    ys = [0.0, 0.0, 0.0, 3.0, 3.0, 3.0, 1.0, 2.0, 1.5, 1.5, 1.5, 1.5]
    tris = trifinder(xs, ys)
    assert_array_equal(tris, [0, 2, 4, 13, 15, 17, 3, 14, 6, 7, 10, 11])

    # Test points exactly on boundary corners of masked triangulation.
    xs = [0.0, 3.0]
    ys = [0.0, 3.0]
    tris = trifinder(xs, ys)
    assert_array_equal(tris, [0, 17])

    # Test triangles with horizontal colinear points.  These are not valid
    # triangulations, but we try to deal with the simplest violations.
    delta = 0.0  # If +ve, triangulation is OK, if -ve triangulation invalid,
                 # if zero have colinear points but should pass tests anyway.
    x = [1.5, 0,  1,  2, 3, 1.5,   1.5]
    y = [-1,  0,  0,  0, 0, delta, 1]
    triangles = [[0, 2, 1], [0, 3, 2], [0, 4, 3], [1, 2, 5], [2, 3, 5],
                 [3, 4, 5], [1, 5, 6], [4, 6, 5]]
    triang = mtri.Triangulation(x, y, triangles)
    trifinder = triang.get_trifinder()

    xs = [-0.1, 0.4, 0.9, 1.4, 1.9, 2.4, 2.9]
    ys = [-0.1, 0.1]
    xs, ys = np.meshgrid(xs, ys)
    tris = trifinder(xs, ys)
    assert_array_equal(tris, [[-1, 0, 0, 1, 1, 2, -1],
                              [-1, 6, 6, 6, 7, 7, -1]])

    # Test triangles with vertical colinear points.  These are not valid
    # triangulations, but we try to deal with the simplest violations.
    delta = 0.0  # If +ve, triangulation is OK, if -ve triangulation invalid,
                # if zero have colinear points but should pass tests anyway.
    x = [-1, -delta, 0,  0,  0, 0, 1]
    y = [1.5, 1.5,   0,  1,  2, 3, 1.5]
    triangles = [[0, 1, 2], [0, 1, 5], [1, 2, 3], [1, 3, 4], [1, 4, 5],
                 [2, 6, 3], [3, 6, 4], [4, 6, 5]]
    triang = mtri.Triangulation(x, y, triangles)
    trifinder = triang.get_trifinder()

    xs = [-0.1, 0.1]
    ys = [-0.1, 0.4, 0.9, 1.4, 1.9, 2.4, 2.9]
    xs, ys = np.meshgrid(xs, ys)
    tris = trifinder(xs, ys)
    assert_array_equal(tris, [[-1, -1], [0, 5], [0, 5], [0, 6], [1, 6], [1, 7],
                              [-1, -1]])

    # Test that changing triangulation by setting a mask causes the trifinder
    # to be reinitialised.
    x = [0, 1, 0, 1]
    y = [0, 0, 1, 1]
    triangles = [[0, 1, 2], [1, 3, 2]]
    triang = mtri.Triangulation(x, y, triangles)
    trifinder = triang.get_trifinder()

    xs = [-0.2, 0.2, 0.8, 1.2]
    ys = [ 0.5, 0.5, 0.5, 0.5]
    tris = trifinder(xs, ys)
    assert_array_equal(tris, [-1, 0, 1, -1])

    triang.set_mask([1, 0])
    assert_equal(trifinder, triang.get_trifinder())
    tris = trifinder(xs, ys)
    assert_array_equal(tris, [-1, -1, 1, -1])


def test_triinterp():
    # Test points within triangles of masked triangulation.
    x, y = np.meshgrid(np.arange(4), np.arange(4))
    x = x.ravel()
    y = y.ravel()
    z = 1.23*x - 4.79*y
    triangles = [[0, 1, 4], [1, 5, 4], [1, 2, 5], [2, 6, 5], [2, 3, 6],
                 [3, 7, 6], [4, 5, 8], [5, 9, 8], [5, 6, 9], [6, 10, 9],
                 [6, 7, 10], [7, 11, 10], [8, 9, 12], [9, 13, 12], [9, 10, 13],
                 [10, 14, 13], [10, 11, 14], [11, 15, 14]]
    mask = np.zeros(len(triangles))
    mask[8:10] = 1
    triang = mtri.Triangulation(x, y, triangles, mask)
    linear_interp = mtri.LinearTriInterpolator(triang, z)
    cubic_min_E = mtri.CubicTriInterpolator(triang, z)
    cubic_geom = mtri.CubicTriInterpolator(triang, z, kind='geom')

    xs = np.linspace(0.25, 2.75, 6)
    ys = [0.25, 0.75, 2.25, 2.75]
    xs, ys = np.meshgrid(xs, ys)  # Testing arrays with array.ndim = 2
    for interp in (linear_interp, cubic_min_E, cubic_geom):
        zs = interp(xs, ys)
        assert_array_almost_equal(zs, (1.23*xs - 4.79*ys))

    # Test points outside triangulation.
    xs = [-0.25, 1.25, 1.75, 3.25]
    ys = xs
    xs, ys = np.meshgrid(xs, ys)
    for interp in (linear_interp, cubic_min_E, cubic_geom):
        zs = linear_interp(xs, ys)
        assert_array_equal(zs.mask, [[True]*4]*4)

    # Test mixed configuration (outside / inside).
    xs = np.linspace(0.25, 1.75, 6)
    ys = [0.25, 0.75, 1.25, 1.75]
    xs, ys = np.meshgrid(xs, ys)
    for interp in (linear_interp, cubic_min_E, cubic_geom):
        zs = interp(xs, ys)
        matest.assert_array_almost_equal(zs, (1.23*xs - 4.79*ys))
        mask = (xs >= 1) * (xs <= 2) * (ys >= 1) * (ys <= 2)
        assert_array_equal(zs.mask, mask)

    # 2nd order patch test: on a grid with an 'arbitrary shaped' triangle,
    # patch test shall be exact for quadratic functions and cubic
    # interpolator if *kind* = user
    (a, b, c) = (1.23, -4.79, 0.6)

    def quad(x, y):
        return a*(x-0.5)**2 + b*(y-0.5)**2 + c*x*y

    def gradient_quad(x, y):
        return (2*a*(x-0.5) + c*y, 2*b*(y-0.5) + c*x)

    x = np.array([0.2, 0.33367, 0.669, 0., 1., 1., 0.])
    y = np.array([0.3, 0.80755, 0.4335, 0., 0., 1., 1.])
    triangles = np.array([[0, 1, 2], [3, 0, 4], [4, 0, 2], [4, 2, 5],
                          [1, 5, 2], [6, 5, 1], [6, 1, 0], [6, 0, 3]])
    triang = mtri.Triangulation(x, y, triangles)
    z = quad(x, y)
    dz = gradient_quad(x, y)
    # test points for 2nd order patch test
    xs = np.linspace(0., 1., 5)
    ys = np.linspace(0., 1., 5)
    xs, ys = np.meshgrid(xs, ys)
    cubic_user = mtri.CubicTriInterpolator(triang, z, kind='user', dz=dz)
    interp_zs = cubic_user(xs, ys)
    assert_array_almost_equal(interp_zs, quad(xs, ys))
    (interp_dzsdx, interp_dzsdy) = cubic_user.gradient(x, y)
    (dzsdx, dzsdy) = gradient_quad(x, y)
    assert_array_almost_equal(interp_dzsdx, dzsdx)
    assert_array_almost_equal(interp_dzsdy, dzsdy)

    # Cubic improvement: cubic interpolation shall perform better than linear
    # on a sufficiently dense mesh for a quadratic function.
    n = 11
    x, y = np.meshgrid(np.linspace(0., 1., n+1), np.linspace(0., 1., n+1))
    x = x.ravel()
    y = y.ravel()
    z = quad(x, y)
    triang = mtri.Triangulation(x, y, triangles=meshgrid_triangles(n+1))
    xs, ys = np.meshgrid(np.linspace(0.1, 0.9, 5), np.linspace(0.1, 0.9, 5))
    xs = xs.ravel()
    ys = ys.ravel()
    linear_interp = mtri.LinearTriInterpolator(triang, z)
    cubic_min_E = mtri.CubicTriInterpolator(triang, z)
    cubic_geom = mtri.CubicTriInterpolator(triang, z, kind='geom')
    zs = quad(xs, ys)
    diff_lin = np.abs(linear_interp(xs, ys) - zs)
    for interp in (cubic_min_E, cubic_geom):
        diff_cubic = np.abs(interp(xs, ys) - zs)
        assert(np.max(diff_lin) >= 10.*np.max(diff_cubic))
        assert(np.dot(diff_lin, diff_lin) >=
               100.*np.dot(diff_cubic, diff_cubic))


def test_triinterpcubic_C1_continuity():
    # Below the 4 tests which demonstrate C1 continuity of the
    # TriCubicInterpolator (testing the cubic shape functions on arbitrary
    # triangle):
    #
    # 1) Testing continuity of function & derivatives at corner for all 9
    #    shape functions. Testing also function values at same location.
    # 2) Testing C1 continuity along each edge (as gradient is polynomial of
    #    2nd order, it is sufficient to test at the middle).
    # 3) Testing C1 continuity at triangle barycenter (where the 3 subtriangles
    #    meet)
    # 4) Testing C1 continuity at median 1/3 points (midside between 2
    #    subtriangles)

    # Utility test function check_continuity
    def check_continuity(interpolator, loc, values=None):
        """
        Checks the continuity of interpolator (and its derivatives) near
        location loc. Can check the value at loc itself if *values* is
        provided.

        *interpolator* TriInterpolator
        *loc* location to test (x0, y0)
        *values* (optional) array [z0, dzx0, dzy0] to check the value at *loc*
        """
        n_star = 24       # Number of continuity points in a boundary of loc
        epsilon = 1.e-10  # Distance for loc boundary
        k = 100.          # Continuity coefficient
        (loc_x, loc_y) = loc
        star_x = loc_x + epsilon*np.cos(np.linspace(0., 2*np.pi, n_star))
        star_y = loc_y + epsilon*np.sin(np.linspace(0., 2*np.pi, n_star))
        z = interpolator([loc_x], [loc_y])[0]
        (dzx, dzy) = interpolator.gradient([loc_x], [loc_y])
        if values is not None:
            assert_array_almost_equal(z, values[0])
            assert_array_almost_equal(dzx[0], values[1])
            assert_array_almost_equal(dzy[0], values[2])
        diff_z = interpolator(star_x, star_y) - z
        (tab_dzx, tab_dzy) = interpolator.gradient(star_x, star_y)
        diff_dzx = tab_dzx - dzx
        diff_dzy = tab_dzy - dzy
        assert_array_less(diff_z, epsilon*k)
        assert_array_less(diff_dzx, epsilon*k)
        assert_array_less(diff_dzy, epsilon*k)

    # Drawing arbitrary triangle (a, b, c) inside a unit square.
    (ax, ay) = (0.2, 0.3)
    (bx, by) = (0.33367, 0.80755)
    (cx, cy) = (0.669, 0.4335)
    x = np.array([ax, bx, cx, 0., 1., 1., 0.])
    y = np.array([ay, by, cy, 0., 0., 1., 1.])
    triangles = np.array([[0, 1, 2], [3, 0, 4], [4, 0, 2], [4, 2, 5],
                          [1, 5, 2], [6, 5, 1], [6, 1, 0], [6, 0, 3]])
    triang = mtri.Triangulation(x, y, triangles)

    for idof in range(9):
        z = np.zeros(7, dtype=np.float64)
        dzx = np.zeros(7, dtype=np.float64)
        dzy = np.zeros(7, dtype=np.float64)
        values = np.zeros([3, 3], dtype=np.float64)
        case = idof//3
        values[case, idof % 3] = 1.0
        if case == 0:
            z[idof] = 1.0
        elif case == 1:
            dzx[idof % 3] = 1.0
        elif case == 2:
            dzy[idof % 3] = 1.0
        interp = mtri.CubicTriInterpolator(triang, z, kind='user',
                                           dz=(dzx, dzy))
        # Test 1) Checking values and continuity at nodes
        check_continuity(interp, (ax, ay), values[:, 0])
        check_continuity(interp, (bx, by), values[:, 1])
        check_continuity(interp, (cx, cy), values[:, 2])
        # Test 2) Checking continuity at midside nodes
        check_continuity(interp, ((ax+bx)*0.5, (ay+by)*0.5))
        check_continuity(interp, ((ax+cx)*0.5, (ay+cy)*0.5))
        check_continuity(interp, ((cx+bx)*0.5, (cy+by)*0.5))
        # Test 3) Checking continuity at barycenter
        check_continuity(interp, ((ax+bx+cx)/3., (ay+by+cy)/3.))
        # Test 4) Checking continuity at median 1/3-point
        check_continuity(interp, ((4.*ax+bx+cx)/6., (4.*ay+by+cy)/6.))
        check_continuity(interp, ((ax+4.*bx+cx)/6., (ay+4.*by+cy)/6.))
        check_continuity(interp, ((ax+bx+4.*cx)/6., (ay+by+4.*cy)/6.))


def test_triinterpcubic_cg_solver():
    # Now 3 basic tests of the Sparse CG solver, used for
    # TriCubicInterpolator with *kind* = 'min_E'
    # 1) A commonly used test involves a 2d Poisson matrix.
    def poisson_sparse_matrix(n, m):
        """
        Sparse Poisson matrix.

        Returns the sparse matrix in coo format resulting from the
        discretisation of the 2-dimensional Poisson equation according to a
        finite difference numerical scheme on a uniform (n, m) grid.
        Size of the matrix: (n*m, n*m)
        """
        l = m*n
        rows = np.concatenate([
            np.arange(l, dtype=np.int32),
            np.arange(l-1, dtype=np.int32), np.arange(1, l, dtype=np.int32),
            np.arange(l-n, dtype=np.int32), np.arange(n, l, dtype=np.int32)])
        cols = np.concatenate([
            np.arange(l, dtype=np.int32),
            np.arange(1, l, dtype=np.int32), np.arange(l-1, dtype=np.int32),
            np.arange(n, l, dtype=np.int32), np.arange(l-n, dtype=np.int32)])
        vals = np.concatenate([
            4*np.ones(l, dtype=np.float64),
            -np.ones(l-1, dtype=np.float64), -np.ones(l-1, dtype=np.float64),
            -np.ones(l-n, dtype=np.float64), -np.ones(l-n, dtype=np.float64)])
        # In fact +1 and -1 diags have some zeros
        vals[l:2*l-1][m-1::m] = 0.
        vals[2*l-1:3*l-2][m-1::m] = 0.
        return vals, rows, cols, (n*m, n*m)

    # Instantiating a sparse Poisson matrix of size 48 x 48:
    (n, m) = (12, 4)
    mat = mtri.triinterpolate._Sparse_Matrix_coo(*poisson_sparse_matrix(n, m))
    mat.compress_csc()
    mat_dense = mat.to_dense()
    # Testing a sparse solve for all 48 basis vector
    for itest in range(n*m):
        b = np.zeros(n*m, dtype=np.float64)
        b[itest] = 1.
        x, _ = mtri.triinterpolate._cg(A=mat, b=b, x0=np.zeros(n*m),
                                       tol=1.e-10)
        assert_array_almost_equal(np.dot(mat_dense, x), b)

    # 2) Same matrix with inserting 2 rows - cols with null diag terms
    # (but still linked with the rest of the matrix by extra-diag terms)
    (i_zero, j_zero) = (12, 49)
    vals, rows, cols, _ = poisson_sparse_matrix(n, m)
    rows = rows + 1*(rows >= i_zero) + 1*(rows >= j_zero)
    cols = cols + 1*(cols >= i_zero) + 1*(cols >= j_zero)
    # adding extra-diag terms
    rows = np.concatenate([rows, [i_zero, i_zero-1, j_zero, j_zero-1]])
    cols = np.concatenate([cols, [i_zero-1, i_zero, j_zero-1, j_zero]])
    vals = np.concatenate([vals, [1., 1., 1., 1.]])
    mat = mtri.triinterpolate._Sparse_Matrix_coo(vals, rows, cols,
                                                 (n*m + 2, n*m + 2))
    mat.compress_csc()
    mat_dense = mat.to_dense()
    # Testing a sparse solve for all 50 basis vec
    for itest in range(n*m + 2):
        b = np.zeros(n*m + 2, dtype=np.float64)
        b[itest] = 1.
        x, _ = mtri.triinterpolate._cg(A=mat, b=b, x0=np.ones(n*m + 2),
                                       tol=1.e-10)
        assert_array_almost_equal(np.dot(mat_dense, x), b)

    # 3) Now a simple test that summation of duplicate (i.e. with same rows,
    # same cols) entries occurs when compressed.
    vals = np.ones(17, dtype=np.float64)
    rows = np.array([0, 1, 2, 0, 0, 1, 1, 2, 2, 2, 2, 2, 1, 1, 1, 1, 1],
                    dtype=np.int32)
    cols = np.array([0, 1, 2, 1, 1, 0, 0, 1, 1, 1, 1, 1, 2, 2, 2, 2, 2],
                    dtype=np.int32)
    dim = (3, 3)
    mat = mtri.triinterpolate._Sparse_Matrix_coo(vals, rows, cols, dim)
    mat.compress_csc()
    mat_dense = mat.to_dense()
    assert_array_almost_equal(mat_dense, np.array([
        [1., 2., 0.], [2., 1., 5.], [0., 5., 1.]], dtype=np.float64))


def test_triinterpcubic_geom_weights():
    # Tests to check computation of weights for _DOF_estimator_geom:
    # The weight sum per triangle can be 1. (in case all angles < 90 degrees)
    # or (2*w_i) where w_i = 1-alpha_i/np.pi is the weight of apex i ; alpha_i
    # is the apex angle > 90 degrees.
    (ax, ay) = (0., 1.687)
    x = np.array([ax, 0.5*ax, 0., 1.])
    y = np.array([ay, -ay, 0., 0.])
    z = np.zeros(4, dtype=np.float64)
    triangles = [[0, 2, 3], [1, 3, 2]]
    sum_w = np.zeros([4, 2])  # 4 possibilities ; 2 triangles
    for theta in np.linspace(0., 2*np.pi, 14):  # rotating the figure...
        x_rot = np.cos(theta)*x + np.sin(theta)*y
        y_rot = -np.sin(theta)*x + np.cos(theta)*y
        triang = mtri.Triangulation(x_rot, y_rot, triangles)
        cubic_geom = mtri.CubicTriInterpolator(triang, z, kind='geom')
        dof_estimator = mtri.triinterpolate._DOF_estimator_geom(cubic_geom)
        weights = dof_estimator.compute_geom_weights()
        # Testing for the 4 possibilities...
        sum_w[0, :] = np.sum(weights, 1) - 1
        for itri in range(3):
            sum_w[itri+1, :] = np.sum(weights, 1) - 2*weights[:, itri]
        assert_array_almost_equal(np.min(np.abs(sum_w), axis=0),
                                  np.array([0., 0.], dtype=np.float64))


def test_triinterp_colinear():
    # Tests interpolating inside a triangulation with horizontal colinear
    # points (refer also to the tests :func:`test_trifinder` ).
    #
    # These are not valid triangulations, but we try to deal with the
    # simplest violations (i. e. those handled by default TriFinder).
    #
    # Note that the LinearTriInterpolator and the CubicTriInterpolator with
    # kind='min_E' or 'geom' still pass a linear patch test.
    # We also test interpolation inside a  flat triangle, by forcing
    # *tri_index* in a call to :meth:`_interpolate_multikeys`.

    delta = 0.  # If +ve, triangulation is OK, if -ve triangulation invalid,
                # if zero have colinear points but should pass tests anyway.
    x0 = np.array([1.5, 0,  1,  2, 3, 1.5,   1.5])
    y0 = np.array([-1,  0,  0,  0, 0, delta, 1])

    # We test different affine transformations of the initial figure ; to
    # avoid issues related to round-off errors we only use integer
    # coefficients (otherwise the Triangulation might become invalid even with
    # delta == 0).
    transformations = [[1, 0], [0, 1], [1, 1], [1, 2], [-2, -1], [-2, 1]]
    for transformation in transformations:
        x_rot = transformation[0]*x0 + transformation[1]*y0
        y_rot = -transformation[1]*x0 + transformation[0]*y0
        (x, y) = (x_rot, y_rot)
        z = 1.23*x - 4.79*y
        triangles = [[0, 2, 1], [0, 3, 2], [0, 4, 3], [1, 2, 5], [2, 3, 5],
                     [3, 4, 5], [1, 5, 6], [4, 6, 5]]
        triang = mtri.Triangulation(x, y, triangles)
        xs = np.linspace(np.min(triang.x), np.max(triang.x), 20)
        ys = np.linspace(np.min(triang.y), np.max(triang.y), 20)
        xs, ys = np.meshgrid(xs, ys)
        xs = xs.ravel()
        ys = ys.ravel()
        mask_out = (triang.get_trifinder()(xs, ys) == -1)
        zs_target = np.ma.array(1.23*xs - 4.79*ys, mask=mask_out)

        linear_interp = mtri.LinearTriInterpolator(triang, z)
        cubic_min_E = mtri.CubicTriInterpolator(triang, z)
        cubic_geom = mtri.CubicTriInterpolator(triang, z, kind='geom')

        for interp in (linear_interp, cubic_min_E, cubic_geom):
            zs = interp(xs, ys)
            assert_array_almost_equal(zs_target, zs)

        # Testing interpolation inside the flat triangle number 4: [2, 3, 5]
        # by imposing *tri_index* in a call to :meth:`_interpolate_multikeys`
        itri = 4
        pt1 = triang.triangles[itri, 0]
        pt2 = triang.triangles[itri, 1]
        xs = np.linspace(triang.x[pt1], triang.x[pt2], 10)
        ys = np.linspace(triang.y[pt1], triang.y[pt2], 10)
        zs_target = 1.23*xs - 4.79*ys
        for interp in (linear_interp, cubic_min_E, cubic_geom):
            zs, = interp._interpolate_multikeys(
                xs, ys, tri_index=itri*np.ones(10, dtype=np.int32))
            assert_array_almost_equal(zs_target, zs)


def test_triinterp_transformations():
    # 1) Testing that the interpolation scheme is invariant by rotation of the
    # whole figure.
    # Note: This test is non-trivial for a CubicTriInterpolator with
    # kind='min_E'. It does fail for a non-isotropic stiffness matrix E of
    # :class:`_ReducedHCT_Element` (tested with E=np.diag([1., 1., 1.])), and
    # provides a good test for :meth:`get_Kff_and_Ff`of the same class.
    #
    # 2) Also testing that the interpolation scheme is invariant by expansion
    # of the whole figure along one axis.
    n_angles = 20
    n_radii = 10
    min_radius = 0.15

    def z(x, y):
        r1 = np.sqrt((0.5-x)**2 + (0.5-y)**2)
        theta1 = np.arctan2(0.5-x, 0.5-y)
        r2 = np.sqrt((-x-0.2)**2 + (-y-0.2)**2)
        theta2 = np.arctan2(-x-0.2, -y-0.2)
        z = -(2*(np.exp((r1/10)**2)-1)*30. * np.cos(7.*theta1) +
              (np.exp((r2/10)**2)-1)*30. * np.cos(11.*theta2) +
              0.7*(x**2 + y**2))
        return (np.max(z)-z)/(np.max(z)-np.min(z))

    # First create the x and y coordinates of the points.
    radii = np.linspace(min_radius, 0.95, n_radii)
    angles = np.linspace(0 + n_angles, 2*np.pi + n_angles,
                         n_angles, endpoint=False)
    angles = np.repeat(angles[..., np.newaxis], n_radii, axis=1)
    angles[:, 1::2] += np.pi/n_angles
    x0 = (radii*np.cos(angles)).flatten()
    y0 = (radii*np.sin(angles)).flatten()
    triang0 = mtri.Triangulation(x0, y0)  # Delaunay triangulation
    z0 = z(x0, y0)

    # Then create the test points
    xs0 = np.linspace(-1., 1., 23)
    ys0 = np.linspace(-1., 1., 23)
    xs0, ys0 = np.meshgrid(xs0, ys0)
    xs0 = xs0.ravel()
    ys0 = ys0.ravel()

    interp_z0 = {}
    for i_angle in range(2):
        # Rotating everything
        theta = 2*np.pi / n_angles * i_angle
        x = np.cos(theta)*x0 + np.sin(theta)*y0
        y = -np.sin(theta)*x0 + np.cos(theta)*y0
        xs = np.cos(theta)*xs0 + np.sin(theta)*ys0
        ys = -np.sin(theta)*xs0 + np.cos(theta)*ys0
        triang = mtri.Triangulation(x, y, triang0.triangles)
        linear_interp = mtri.LinearTriInterpolator(triang, z0)
        cubic_min_E = mtri.CubicTriInterpolator(triang, z0)
        cubic_geom = mtri.CubicTriInterpolator(triang, z0, kind='geom')
        dic_interp = {'lin': linear_interp,
                      'min_E': cubic_min_E,
                      'geom': cubic_geom}
        # Testing that the interpolation is invariant by rotation...
        for interp_key in ['lin', 'min_E', 'geom']:
            interp = dic_interp[interp_key]
            if i_angle == 0:
                interp_z0[interp_key] = interp(xs0, ys0)  # storage
            else:
                interpz = interp(xs, ys)
                matest.assert_array_almost_equal(interpz,
                                                 interp_z0[interp_key])

    scale_factor = 987654.3210
    for scaled_axis in ('x', 'y'):
        # Scaling everything (expansion along scaled_axis)
        if scaled_axis == 'x':
            x = scale_factor * x0
            y = y0
            xs = scale_factor * xs0
            ys = ys0
        else:
            x = x0
            y = scale_factor * y0
            xs = xs0
            ys = scale_factor * ys0
        triang = mtri.Triangulation(x, y, triang0.triangles)
        linear_interp = mtri.LinearTriInterpolator(triang, z0)
        cubic_min_E = mtri.CubicTriInterpolator(triang, z0)
        cubic_geom = mtri.CubicTriInterpolator(triang, z0, kind='geom')
        dic_interp = {'lin': linear_interp,
                      'min_E': cubic_min_E,
                      'geom': cubic_geom}
        # Testing that the interpolation is invariant by expansion along
        # 1 axis...
        for interp_key in ['lin', 'min_E', 'geom']:
            interpz = dic_interp[interp_key](xs, ys)
            matest.assert_array_almost_equal(interpz, interp_z0[interp_key])


@image_comparison(baseline_images=['tri_smooth_contouring'],
                  extensions=['png'], remove_text=True)
def test_tri_smooth_contouring():
    # Image comparison based on example tricontour_smooth_user.
    n_angles = 20
    n_radii = 10
    min_radius = 0.15

    def z(x, y):
        r1 = np.sqrt((0.5-x)**2 + (0.5-y)**2)
        theta1 = np.arctan2(0.5-x, 0.5-y)
        r2 = np.sqrt((-x-0.2)**2 + (-y-0.2)**2)
        theta2 = np.arctan2(-x-0.2, -y-0.2)
        z = -(2*(np.exp((r1/10)**2)-1)*30. * np.cos(7.*theta1) +
              (np.exp((r2/10)**2)-1)*30. * np.cos(11.*theta2) +
              0.7*(x**2 + y**2))
        return (np.max(z)-z)/(np.max(z)-np.min(z))

    # First create the x and y coordinates of the points.
    radii = np.linspace(min_radius, 0.95, n_radii)
    angles = np.linspace(0 + n_angles, 2*np.pi + n_angles,
                         n_angles, endpoint=False)
    angles = np.repeat(angles[..., np.newaxis], n_radii, axis=1)
    angles[:, 1::2] += np.pi/n_angles
    x0 = (radii*np.cos(angles)).flatten()
    y0 = (radii*np.sin(angles)).flatten()
    triang0 = mtri.Triangulation(x0, y0)  # Delaunay triangulation
    z0 = z(x0, y0)
    xmid = x0[triang0.triangles].mean(axis=1)
    ymid = y0[triang0.triangles].mean(axis=1)
    mask = np.where(xmid*xmid + ymid*ymid < min_radius*min_radius, 1, 0)
    triang0.set_mask(mask)

    # Then the plot
    refiner = mtri.UniformTriRefiner(triang0)
    tri_refi, z_test_refi = refiner.refine_field(z0, subdiv=4)
    levels = np.arange(0., 1., 0.025)
    plt.triplot(triang0, lw=0.5, color='0.5')
    plt.tricontour(tri_refi, z_test_refi, levels=levels, colors="black")


@image_comparison(baseline_images=['tri_smooth_gradient'],
                  extensions=['png'], remove_text=True)
def test_tri_smooth_gradient():
    # Image comparison based on example trigradient_demo.

    def dipole_potential(x, y):
        """ An electric dipole potential V """
        r_sq = x**2 + y**2
        theta = np.arctan2(y, x)
        z = np.cos(theta)/r_sq
        return (np.max(z)-z) / (np.max(z)-np.min(z))

    # Creating a Triangulation
    n_angles = 30
    n_radii = 10
    min_radius = 0.2
    radii = np.linspace(min_radius, 0.95, n_radii)
    angles = np.linspace(0, 2*np.pi, n_angles, endpoint=False)
    angles = np.repeat(angles[..., np.newaxis], n_radii, axis=1)
    angles[:, 1::2] += np.pi/n_angles
    x = (radii*np.cos(angles)).flatten()
    y = (radii*np.sin(angles)).flatten()
    V = dipole_potential(x, y)
    triang = mtri.Triangulation(x, y)
    xmid = x[triang.triangles].mean(axis=1)
    ymid = y[triang.triangles].mean(axis=1)
    mask = np.where(xmid*xmid + ymid*ymid < min_radius*min_radius, 1, 0)
    triang.set_mask(mask)

    # Refine data - interpolates the electrical potential V
    refiner = mtri.UniformTriRefiner(triang)
    tri_refi, z_test_refi = refiner.refine_field(V, subdiv=3)

    # Computes the electrical field (Ex, Ey) as gradient of -V
    tci = mtri.CubicTriInterpolator(triang, -V)
    (Ex, Ey) = tci.gradient(triang.x, triang.y)
    E_norm = np.sqrt(Ex**2 + Ey**2)

    # Plot the triangulation, the potential iso-contours and the vector field
    plt.figure()
    plt.gca().set_aspect('equal')
    plt.triplot(triang, color='0.8')

    levels = np.arange(0., 1., 0.01)
    cmap = cm.get_cmap(name='hot', lut=None)
    plt.tricontour(tri_refi, z_test_refi, levels=levels, cmap=cmap,
                   linewidths=[2.0, 1.0, 1.0, 1.0])
    # Plots direction of the electrical vector field
    plt.quiver(triang.x, triang.y, Ex/E_norm, Ey/E_norm,
               units='xy', scale=10., zorder=3, color='blue',
               width=0.007, headwidth=3., headlength=4.)


def test_tritools():
    # Tests TriAnalyzer.scale_factors on masked triangulation
    # Tests circle_ratios on equilateral and right-angled triangle.
    x = np.array([0., 1., 0.5, 0., 2.])
    y = np.array([0., 0., 0.5*np.sqrt(3.), -1., 1.])
    triangles = np.array([[0, 1, 2], [0, 1, 3], [1, 2, 4]], dtype=np.int32)
    mask = np.array([False, False, True], dtype=np.bool)
    triang = mtri.Triangulation(x, y, triangles, mask=mask)
    analyser = mtri.TriAnalyzer(triang)
    assert_array_almost_equal(analyser.scale_factors,
                              np.array([1., 1./(1.+0.5*np.sqrt(3.))]))
    assert_array_almost_equal(
        analyser.circle_ratios(rescale=False),
        np.ma.masked_array([0.5, 1./(1.+np.sqrt(2.)), np.nan], mask))

    # Tests circle ratio of a flat triangle
    x = np.array([0., 1., 2.])
    y = np.array([1., 1.+3., 1.+6.])
    triangles = np.array([[0, 1, 2]], dtype=np.int32)
    triang = mtri.Triangulation(x, y, triangles)
    analyser = mtri.TriAnalyzer(triang)
    assert_array_almost_equal(analyser.circle_ratios(), np.array([0.]))

    # Tests TriAnalyzer.get_flat_tri_mask
    # Creates a triangulation of [-1, 1] x [-1, 1] with contiguous groups of
    # 'flat' triangles at the 4 corners and at the center. Checks that only
    # those at the borders are eliminated by TriAnalyzer.get_flat_tri_mask
    n = 9

    def power(x, a):
        return np.abs(x)**a*np.sign(x)

    x = np.linspace(-1., 1., n+1)
    x, y = np.meshgrid(power(x, 2.), power(x, 0.25))
    x = x.ravel()
    y = y.ravel()

    triang = mtri.Triangulation(x, y, triangles=meshgrid_triangles(n+1))
    analyser = mtri.TriAnalyzer(triang)
    mask_flat = analyser.get_flat_tri_mask(0.2)
    verif_mask = np.zeros(162, dtype=np.bool)
    corners_index = [0, 1, 2, 3, 14, 15, 16, 17, 18, 19, 34, 35, 126, 127,
                     142, 143, 144, 145, 146, 147, 158, 159, 160, 161]
    verif_mask[corners_index] = True
    assert_array_equal(mask_flat, verif_mask)

    # Now including a hole (masked triangle) at the center. The center also
    # shall be eliminated by get_flat_tri_mask.
    mask = np.zeros(162, dtype=np.bool)
    mask[80] = True
    triang.set_mask(mask)
    mask_flat = analyser.get_flat_tri_mask(0.2)
    center_index = [44, 45, 62, 63, 78, 79, 80, 81, 82, 83, 98, 99, 116, 117]
    verif_mask[center_index] = True
    assert_array_equal(mask_flat, verif_mask)


def test_trirefine():
    # Testing subdiv=2 refinement
    n = 3
    subdiv = 2
    x = np.linspace(-1., 1., n+1)
    x, y = np.meshgrid(x, x)
    x = x.ravel()
    y = y.ravel()
    mask = np.zeros(2*n**2, dtype=np.bool)
    mask[n**2:] = True
    triang = mtri.Triangulation(x, y, triangles=meshgrid_triangles(n+1),
                                mask=mask)
    refiner = mtri.UniformTriRefiner(triang)
    refi_triang = refiner.refine_triangulation(subdiv=subdiv)
    x_refi = refi_triang.x
    y_refi = refi_triang.y

    n_refi = n * subdiv**2
    x_verif = np.linspace(-1., 1., n_refi+1)
    x_verif, y_verif = np.meshgrid(x_verif, x_verif)
    x_verif = x_verif.ravel()
    y_verif = y_verif.ravel()
    ind1d = np.in1d(np.around(x_verif*(2.5+y_verif), 8),
                    np.around(x_refi*(2.5+y_refi), 8))
    assert_array_equal(ind1d, True)

    # Testing the mask of the refined triangulation
    refi_mask = refi_triang.mask
    refi_tri_barycenter_x = np.sum(refi_triang.x[refi_triang.triangles],
                                   axis=1) / 3.
    refi_tri_barycenter_y = np.sum(refi_triang.y[refi_triang.triangles],
                                   axis=1) / 3.
    tri_finder = triang.get_trifinder()
    refi_tri_indices = tri_finder(refi_tri_barycenter_x,
                                  refi_tri_barycenter_y)
    refi_tri_mask = triang.mask[refi_tri_indices]
    assert_array_equal(refi_mask, refi_tri_mask)

    # Testing that the numbering of triangles does not change the
    # interpolation result.
    x = np.asarray([0.0, 1.0, 0.0, 1.0])
    y = np.asarray([0.0, 0.0, 1.0, 1.0])
    triang = [mtri.Triangulation(x, y, [[0, 1, 3], [3, 2, 0]]),
              mtri.Triangulation(x, y, [[0, 1, 3], [2, 0, 3]])]
    z = np.sqrt((x-0.3)*(x-0.3) + (y-0.4)*(y-0.4))
    # Refining the 2 triangulations and reordering the points
    xyz_data = []
    for i in range(2):
        refiner = mtri.UniformTriRefiner(triang[i])
        refined_triang, refined_z = refiner.refine_field(z, subdiv=1)
        xyz = np.dstack((refined_triang.x, refined_triang.y, refined_z))[0]
        xyz = xyz[np.lexsort((xyz[:, 1], xyz[:, 0]))]
        xyz_data += [xyz]
    assert_array_almost_equal(xyz_data[0], xyz_data[1])


def meshgrid_triangles(n):
    """
    Utility function.
    Returns triangles to mesh a np.meshgrid of n x n points
    """
    tri = []
    for i in range(n-1):
        for j in range(n-1):
            a = i + j*(n)
            b = (i+1) + j*n
            c = i + (j+1)*n
            d = (i+1) + (j+1)*n
            tri += [[a, b, d], [a, d, c]]
    return np.array(tri, dtype=np.int32)


def test_triplot_return():
    # Check that triplot returns the artists it adds
    from matplotlib.figure import Figure
    ax = Figure().add_axes([0.1, 0.1, 0.7, 0.7])
    triang = mtri.Triangulation(
        [0.0, 1.0, 0.0, 1.0], [0.0, 0.0, 1.0, 1.0],
        triangles=[[0, 1, 3], [3, 2, 0]])
    if ax.triplot(triang, "b-") is None:
        raise AssertionError("triplot should return the artist it adds")


def test_trirefiner_fortran_contiguous_triangles():
    # github issue 4180.  Test requires two arrays of triangles that are
    # identical except that one is C-contiguous and one is fortran-contiguous.
    triangles1 = np.array([[2, 0, 3], [2, 1, 0]])
    assert_false(np.isfortran(triangles1))

    triangles2 = np.array(triangles1, copy=True, order='F')
    assert_true(np.isfortran(triangles2))

    x = np.array([0.39, 0.59, 0.43, 0.32])
    y = np.array([33.99, 34.01, 34.19, 34.18])
    triang1 = mtri.Triangulation(x, y, triangles1)
    triang2 = mtri.Triangulation(x, y, triangles2)

    refiner1 = mtri.UniformTriRefiner(triang1)
    refiner2 = mtri.UniformTriRefiner(triang2)

    fine_triang1 = refiner1.refine_triangulation(subdiv=1)
    fine_triang2 = refiner2.refine_triangulation(subdiv=1)

    assert_array_equal(fine_triang1.triangles, fine_triang2.triangles)


def test_qhull_triangle_orientation():
    # github issue 4437.
    xi = np.linspace(-2, 2, 100)
    x, y = map(np.ravel, np.meshgrid(xi, xi))
    w = np.logical_and(x > y - 1, np.logical_and(x < -1.95, y > -1.2))
    x, y = x[w], y[w]
    theta = np.radians(25)
    x1 = x*np.cos(theta) - y*np.sin(theta)
    y1 = x*np.sin(theta) + y*np.cos(theta)

    # Calculate Delaunay triangulation using Qhull.
    triang = mtri.Triangulation(x1, y1)

    # Neighbors returned by Qhull.
    qhull_neighbors = triang.neighbors

    # Obtain neighbors using own C++ calculation.
    triang._neighbors = None
    own_neighbors = triang.neighbors

    assert_array_equal(qhull_neighbors, own_neighbors)


if __name__ == '__main__':
    import nose
    nose.runmodule(argv=['-s', '--with-doctest'], exit=False)
