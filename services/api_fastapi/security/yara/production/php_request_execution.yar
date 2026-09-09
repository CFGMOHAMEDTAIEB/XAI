// Narrow defensive detections for PHP source executing raw HTTP input.
// These rules supplement ClamAV; they are not general malware coverage.
// Anchor PHP source at the start to avoid treating XAIC/binary/document content
// containing quoted PHP examples as an executable PHP upload.

private rule XAI_PHP_Source
{
    strings:
        $php = "<?php" nocase
    condition:
        $php at 0 or (uint8(0) == 0xef and uint8(1) == 0xbb and
                      uint8(2) == 0xbf and $php at 3)
}

rule XAI_PHP_Direct_Request_Eval
{
    meta:
        description = "PHP source directly evaluates raw HTTP request input"
        author = "XAI project"
        date = "2026-09-08"
        scope = "Narrow dangerous web-shell behavior; not comprehensive malware coverage"
    strings:
        $execute = /\beval\s*\(\s*(base64_decode\s*\(\s*)?\$_(POST|GET|REQUEST|COOKIE)\s*\[/ nocase
    condition:
        XAI_PHP_Source and $execute
}

rule XAI_PHP_Direct_Request_Command
{
    meta:
        description = "PHP source passes raw HTTP request input to an OS command function"
        author = "XAI project"
        date = "2026-09-08"
        scope = "Narrow dangerous web-shell behavior; not comprehensive malware coverage"
    strings:
        $execute = /\b(system|shell_exec|passthru|exec|popen)\s*\(\s*\$_(POST|GET|REQUEST|COOKIE)\s*\[/ nocase
    condition:
        XAI_PHP_Source and $execute
}
