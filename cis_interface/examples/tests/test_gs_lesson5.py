import os
from cis_interface.examples.tests import TestExample


class TestExampleGS5(TestExample):
    r"""Test the Getting Started Lesson 5 example."""

    def __init__(self, *args, **kwargs):
        super(TestExampleGS5, self).__init__(*args, **kwargs)
        self._name = 'gs_lesson5'

    @property
    def input_files(self):
        r"""Input file."""
        return [os.path.join(self.yamldir, 'Input', 'input.txt')]

    @property
    def output_files(self):
        r"""Output file."""
        return [os.path.join(self.yamldir, 'output.txt')]
