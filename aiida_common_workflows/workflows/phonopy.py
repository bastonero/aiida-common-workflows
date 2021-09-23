# -*- coding: utf-8 -*-
"""Phonopy workflow that can use any code plugin implementing the common relax workflow."""
from aiida.plugins import WorkflowFactory

from aiida_common_workflows.workflows.relax.generator import RelaxType, SpinType, ElectronicType
from aiida_common_workflows.workflows.eos import validate_sub_process_class
from aiida_common_workflows.workflows.dissociation import validate_relax

BasePhonopyWorkChain = WorkflowFactory('phonopy.phonopy.base')


def validate_inputs(value, _):
    """Validate the entire input namespace."""
    # Validate that the provided ``generator_inputs`` are valid for the associated input generator.
    process_class = WorkflowFactory(value['sub_process_class'])
    generator = process_class.get_input_generator()

    try:
        generator.get_builder(value['structure'], **value['generator_inputs'])
    except Exception as exc:  # pylint: disable=broad-except
        return f'`{generator.__class__.__name__}.get_builder()` fails for the provided `generator_inputs`: {exc}'


class CommonPhonopyWorkChain(BasePhonopyWorkChain):
    """Workflow to compute the phonon using phonopy for a given crystal structure."""

    @classmethod
    def define(cls, spec):
        # yapf: disable
        super().define(spec)
        spec.input_namespace('generator_inputs',
            help='The inputs that will be passed to the input generator of the specified `sub_process`.')
        spec.input('generator_inputs.engines', valid_type=dict, non_db=True)
        spec.input('generator_inputs.protocol', valid_type=str, non_db=True,
            help='The protocol to use when determining the workchain inputs.')
        spec.input('generator_inputs.relax_type',
             valid_type=(RelaxType, str), non_db=True, validator=validate_relax,
             help='The type of relaxation to perform.')
        spec.input('generator_inputs.spin_type', valid_type=(SpinType, str), required=False, non_db=True,
            help='The type of spin for the calculation.')
        spec.input('generator_inputs.electronic_type', valid_type=(ElectronicType, str), required=False, non_db=True,
            help='The type of electronics (insulator/metal) for the calculation.')
        spec.input('generator_inputs.magnetization_per_site', valid_type=(list, tuple), required=False, non_db=True,
            help='List containing the initial magnetization per atomic site.')
        spec.input('generator_inputs.threshold_forces', valid_type=float, required=False, non_db=True,
            help='Target threshold for the forces in eV/Å.')
        spec.input_namespace('sub_process', dynamic=True, populate_defaults=False)
        spec.input('sub_process_class', non_db=True, validator=validate_sub_process_class)
        spec.inputs.validator = validate_inputs

    def get_sub_workchain_builder(self, structure, reference_workchain=None):
        """Return the builder for the relax workchain."""
        process_class = WorkflowFactory(self.inputs.sub_process_class)

        builder = process_class.get_input_generator().get_builder(
            structure,
            reference_workchain=reference_workchain,
            **self.inputs.generator_inputs
        )
        builder._update(**self.inputs.get('sub_process', {}))  # pylint: disable=protected-access

        return builder

    def is_nac(self):
        """NAC is not applied."""
        return False

    def _run_force_calculations(self):
        """Run supercell force calculations."""
        self.report("run force calculations")
        for key, supercell in self.ctx.supercells.items():
            label = "force_calc_%s" % key.split("_")[-1]
            builder = self.get_sub_workchain_builder(supercell)
            builder.metadata.label = label
            future = self.submit(builder)
            self.report("{} pk = {}".format(label, future.pk))
            self.to_context(**{label: future})

    def _run_nac_params_calculation(self):
        pass