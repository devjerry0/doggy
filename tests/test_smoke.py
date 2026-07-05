import doggy


def test_package_imports_and_has_version():
    assert isinstance(doggy.__version__, str)
    assert doggy.__version__
