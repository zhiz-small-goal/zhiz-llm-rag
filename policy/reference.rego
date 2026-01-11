package zhiz_llm_rag.reference

import rego.v1

deny[msg] {
  not input.exit_codes.PASS == 0
  msg := sprintf("exit_codes.PASS must be 0, got %v", [input.exit_codes.PASS])
}

deny[msg] {
  not input.exit_codes.FAIL == 2
  msg := sprintf("exit_codes.FAIL must be 2, got %v", [input.exit_codes.FAIL])
}

deny[msg] {
  not input.exit_codes.ERROR == 3
  msg := sprintf("exit_codes.ERROR must be 3, got %v", [input.exit_codes.ERROR])
}

deny[msg] {
  input.paths.report_dir != "data_processed/build_reports"
  msg := sprintf("paths.report_dir must be data_processed/build_reports, got %v", [input.paths.report_dir])
}

deny[msg] {
  input.paths.gate_report != "gate_report.json"
  msg := sprintf("paths.gate_report must be gate_report.json, got %v", [input.paths.gate_report])
}

deny[msg] {
  not endswith(input.schemas.gate_report, "schemas/gate_report_v1.schema.json")
  msg := sprintf("schemas.gate_report must point to schemas/gate_report_v1.schema.json, got %v", [input.schemas.gate_report])
}

deny[msg] {
  input.policy.enabled == true
  input.policy.conftest.version == ""
  msg := "policy.conftest.version must be set when policy.enabled=true"
}

deny[msg] {
  input.policy.enabled == true
  not input.policy.conftest.inputs
  msg := "policy.conftest.inputs must be set when policy.enabled=true"
}
