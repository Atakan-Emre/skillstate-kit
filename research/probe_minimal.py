"""Read-only review probes; fake tools, temporary storage, no model/network calls."""
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent / 'skill-state-minimal' / 'src'))
from skill_state import SkillStateRuntime, ExecutionResult, build_prompt

def make(model, executor=None, **options):
    return SkillStateRuntime(skill='Process the current request.', initial_state={'count': 0},
        model=model, validator=lambda s: None,
        executor=executor or (lambda a: ExecutionResult(True, {'ok': True})),
        allowed_actions={'store'}, **options)

def decision(count=1, **args):
    return {'state_patch': {'count': count}, 'action': {'name': 'store', 'arguments': args}}

results = {}
prompts = []
responses = iter([{'invalid': True}, decision()])
def retry_model(prompt):
    prompts.append(json.loads(prompt))
    return next(responses)
make(retry_model, max_retries=1).step({'request_id': 'unique-request'})
results['retry_loses_original_observation'] = 'unique-request' not in json.dumps(prompts[1])

seen = []
make(lambda p: decision(quantity='not-an-integer'),
     lambda a: seen.append(a.arguments) or ExecutionResult(True, {})).step({})
results['no_per_tool_argument_schema'] = seen == [{'quantity': 'not-an-integer'}]

with TemporaryDirectory() as tmp:
    state_file, audit_file = Path(tmp)/'state.json', Path(tmp)/'audit.jsonl'
    runtime = make(lambda p: decision(), state_path=state_file, audit_path=audit_file)
    with patch('skill_state.runtime._append_jsonl', side_effect=OSError('simulated audit failure')):
        try:
            runtime.step({})
        except OSError:
            pass
        else:
            raise AssertionError('expected audit error')
    results['audit_error_after_state_commit'] = runtime.state == {'count': 1} and json.loads(state_file.read_text()) == {'count': 1}

with TemporaryDirectory() as tmp:
    effects = []
    def uncertain(a):
        effects.append('effect happened')
        raise TimeoutError('response lost')
    runtime = make(lambda p: decision(), uncertain, audit_path=Path(tmp)/'audit.jsonl')
    try:
        runtime.step({})
    except TimeoutError:
        pass
    results['executor_exception_without_pending_journal'] = bool(effects) and not (Path(tmp)/'audit.jsonl').exists()

results['large_observation_accepted_bytes'] = len(build_prompt('skill', {}, 'x'*1_000_000).encode())
assert all(value is True for key,value in results.items() if key != 'large_observation_accepted_bytes')
assert results['large_observation_accepted_bytes'] > 1_000_000
print(json.dumps(results, indent=2))
