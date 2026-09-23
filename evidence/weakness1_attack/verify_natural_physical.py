"""Verify the completed natural-calendar timed-work profile."""

import sys

sys.dont_write_bytecode = True

import natural_physical as natural
from verify_physical import verify_run


def main() -> None:
    bundle = natural.validate_preflight()
    expected_fixed = natural.load_and_transform_input(bundle)
    verify_run(
        run_dir=natural.RUN_DIR,
        profile="natural_original_calendar",
        expected_protocol=natural.physical_protocol(bundle),
        expected_input_sha256=bundle["artifact_hashes"][natural.NATURAL_INPUT.name],
        expected_jobs=len(expected_fixed["job_id"]),
        input_path=natural.NATURAL_INPUT,
        expected_fixed=expected_fixed,
        expected_protocol_version=3,
        expected_upstream={
            "protocol": bundle["metadata"]["protocol"],
            "input_sha256": bundle["artifact_hashes"][natural.NATURAL_INPUT.name],
            "metadata_sha256": bundle["artifact_hashes"][natural.NATURAL_METADATA.name],
            "gate": bundle["gate"],
        },
    )


if __name__ == "__main__":
    main()
