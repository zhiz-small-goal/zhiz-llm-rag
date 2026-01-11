package zhiz_llm_rag.ci_workflow

import rego.v1

# Rego v1 syntax (conftest v0.60+ defaults to Rego v1).
# We avoid dot-access to the key "with" because "with" is a Rego keyword.

deny contains msg if {
  not has_gate_step
  msg := "ci.yml must include a step running tools/gate.py"
}

deny contains msg if {
  not has_upload_gate_report
  msg := "ci.yml must upload data_processed/build_reports/gate_report.json (preferably with if: always())"
}

has_gate_step if {
  some i
  step := input.jobs.test.steps[i]
  step.run
  contains(lower(step.run), "tools/gate.py")
}

has_upload_gate_report if {
  some i
  step := input.jobs.test.steps[i]
  step.uses
  contains(step.uses, "actions/upload-artifact")

  # "with" is a reserved keyword in Rego; access the YAML key via brackets.
  step["with"]
  path := step["with"]["path"]
  contains(path, "data_processed/build_reports/gate_report.json")
}
