"""Real production YARA compilation/matching; samples are never executed."""
from pathlib import Path
import pytest
from app import security_scanner as scanner

@pytest.fixture(scope='module')
def production_rules():
    path = Path(__file__).resolve().parents[1] / 'security/yara/production'
    return scanner.load_yara_rules(str(path))

@pytest.mark.parametrize('data,expected', [
    (b'<?php eval($_POST["code"]);', 'XAI_PHP_Direct_Request_Eval'),
    (b'<?php eval(base64_decode($_REQUEST["code"]));', 'XAI_PHP_Direct_Request_Eval'),
    (b'\xef\xbb\xbf<?php system($_GET["command"]);', 'XAI_PHP_Direct_Request_Command'),
    (b'<?PHP shell_exec ( $_COOKIE ["command"] );', 'XAI_PHP_Direct_Request_Command'),
])
def test_detects_direct_request_execution(production_rules, data, expected):
    assert {m.rule for m in production_rules.match(data=data)} == {expected}

@pytest.mark.parametrize('data', [
    b'XAI known-clean text fixture\n' * 128,
    b'{"name":"fixture","values":[1,2,3]}',
    b'name,value\nalpha,1\nbeta,2\n',
    b'<?php echo htmlspecialchars($_GET["name"], ENT_QUOTES, "UTF-8");',
    b'<?php $example = "No dynamic execution"; echo $example;',
    b'XAIC\x06<?php eval($_POST["code"]);',
    b'Example documentation: <?php system($_GET["command"]);',
    b'XAI_SECURITY_TEST_MARKER',
])
def test_clean_samples_do_not_match(production_rules, data):
    assert production_rules.match(data=data) == []

def test_known_clean_project_files(production_rules):
    repo = Path(__file__).resolve().parents[3]
    for relative in ('README.md', 'engines/XAI-Compress/checkpoints/selector_v2/best.json',
                     'apps/mobile_authenticator_flutter/lib/services/deployment_config.dart'):
        assert production_rules.match(str(repo / relative)) == [], relative

def test_production_rules_used_without_synthetic_fallback(monkeypatch, production_rules):
    path = Path(__file__).resolve().parents[1] / 'security/yara/production'
    monkeypatch.setattr(scanner.settings, 'app_env', 'production')
    monkeypatch.setattr(scanner.settings, 'yara_rules_path', str(path))
    assert scanner.configured_rules() is production_rules
    assert all(r.identifier != 'XAI_Synthetic_Security_Test' for r in production_rules)
