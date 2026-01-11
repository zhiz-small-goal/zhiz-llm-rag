package zhiz_llm_rag.ci_workflow

import rego.v1

default deny := []

deny[msg] {
  not has_gate_step
  msg := "ci.yml must include a step running tools/gate.py"
}

deny[msg] {
  not has_upload_gate_report
  msg := "ci.yml must upload data_processed/build_reports/gate_report.json (preferably with if: always())"
}

has_gate_step {
  some i
  step := input.jobs.test.steps[i]
  step.run
  contains(lower(step.run), "tools/gate.py")
}

has_upload_gate_report {
  some i
  step := input.jobs.test.steps[i]
  step.uses
  contains(step.uses, "actions/upload-artifact")
  step.with.path
  contains(step.with.path, "data_processed/build_reports/gate_report.json")
}
