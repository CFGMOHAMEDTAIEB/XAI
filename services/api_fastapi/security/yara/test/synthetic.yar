rule XAI_Synthetic_Security_Test
{
    meta:
        description = "Harmless synthetic marker for defensive integration tests; not a malware signature"
    strings:
        $marker = "XAI_SECURITY_TEST_MARKER"
    condition:
        $marker
}
