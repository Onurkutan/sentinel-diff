import numpy as np

from sentinel_diff.cva import (
    compute_cva_magnitude,
    compute_difference,
    filter_noise_morphology,
    otsu_threshold,
)


def test_difference_and_magnitude():
    before = np.array([[0.1, 0.5], [0.8, 0.2]])
    after = np.array([[0.4, 0.5], [0.2, 0.9]])
    diff = compute_difference(before, after)
    mag = compute_cva_magnitude(diff)

    assert np.allclose(diff, [[0.3, 0.0], [-0.6, 0.7]])
    assert np.allclose(mag, [[0.3, 0.0], [0.6, 0.7]])


def test_otsu_threshold_bimodal():
    # Construct a clearly bimodal distribution: group A around 0.1, group B around 0.8
    np.random.seed(42)
    group1 = np.random.normal(loc=0.1, scale=0.02, size=500)
    group2 = np.random.normal(loc=0.8, scale=0.02, size=500)
    data = np.concatenate([group1, group2])

    th = otsu_threshold(data)
    # The optimal separation between 0.1 and 0.8 is roughly between 0.3 and 0.6
    assert 0.3 < th < 0.6


def test_filter_noise_morphology():
    # 10x10 array with an isolated 1-pixel dot and a 4x4 contiguous block
    arr = np.zeros((10, 10), dtype=bool)
    arr[1, 1] = True  # Isolated noise pixel
    arr[4:8, 4:8] = True  # 16-pixel contiguous block

    cleaned = filter_noise_morphology(arr, min_pixel_size=9)
    # The isolated pixel should be removed
    assert not cleaned[1, 1]
    # The large component should be preserved
    assert np.all(cleaned[4:8, 4:8])


def test_filter_noise_morphology_preserves_image_border():
    """A region touching the array edge must not lose its outer 1-px rim.

    scipy's default border_value=0 erodes the border during opening; the
    implementation must compensate (edge padding) so that a full-width band
    of water at the top of the image keeps all of its pixels.
    """
    arr = np.zeros((12, 12), dtype=bool)
    arr[:5, :] = True  # 60-pixel band touching top, left and right edges

    cleaned = filter_noise_morphology(arr, min_pixel_size=6)

    assert cleaned.sum() == 60
    assert np.array_equal(cleaned, arr)
