API reference
=============

Only the maintained plugin interface and stage functions are listed here. The bundled legacy implementation is intentionally excluded.

Case definition
---------------

.. autoclass:: tistos_opt.TistosCase
   :members:

.. autoclass:: tistos_opt.case.ParameterDefinition
   :members:

Evaluation stages
-----------------

.. autofunction:: tistos_opt.runtime.prepare

.. autofunction:: tistos_opt.runtime.configure_turbulent

.. autofunction:: tistos_opt.runtime.finalize

.. autofunction:: tistos_opt.stages.main

Runtime checks
--------------

.. autoclass:: tistos_opt.runtime_check.CheckResult
   :members:

.. autofunction:: tistos_opt.runtime_check.run_checks

.. autofunction:: tistos_opt.runtime_check.failed_required_count

.. autofunction:: tistos_opt.runtime_check.format_report
