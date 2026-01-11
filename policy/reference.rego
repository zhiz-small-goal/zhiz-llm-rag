package zhiz_llm_rag.reference

import rego.v1

deny contains msg if {
  input.exit_codes.PASS != 0
  msg := sprintf("exit_codes.PASS must be 0, got %v", [input.exit_codes.PASS])
}

deny contains msg if {
  input.exit_codes.FAIL != 2
  msg := sprintf("exit_codes.FAIL must be 2, got %v", [input.exit_codes.FAIL])
}

deny contains msg if {
  input.exit_codes.ERROR != 3
  msg := sprintf("exit_codes.ERROR must be 3, got %v", [input.exit_codes.ERROR])
}

deny contains msg if {
  input.paths.report_dir != "data_processed/build_reports"
  msg := sprintf("paths.report_dir must be data_processed/build_reports, got %v", [input.paths.report_dir])
}

deny contains msg if {
  input.paths.gate_report != "gate_report.json"
  msg := sprintf("paths.gate_report must be gate_report.json, got %v", [input.paths.gate_report])
}

deny contains msg if {
  not endswith(input.schemas.gate_report, "schemas/gate_report_v1.schema.json")
  msg := sprintf("schemas.gate_report must point to schemas/gate_report_v1.schema.json, got %v", [input.schemas.gate_report])
}

deny contains msg if {
  input.policy.enabled == true
  input.policy.conftest.version == ""
  msg := "policy.conftest.version must be set when policy.enabled=true"
}

deny contains msg if {
  input.policy.enabled == true
  not input.policy.conftest.inputs
  msg := "policy.conftest.inputs must be set when policy.enabled=true"
}
