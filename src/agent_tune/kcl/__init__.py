"""Read and edit KTuner .kcl tune files for supported ECU families.

Each table module describes where its values live inside the decoded save body
and how they are encoded. `decode` reads a file and checks it belongs to a
supported family; `patch` writes a new file with changed values.
"""
