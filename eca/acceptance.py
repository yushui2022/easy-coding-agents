"""Evidence-based child acceptance, without recursive model runs or retries."""
import uuid
from .verification import command_status


def validate_commands(commands):
    if commands is not None and (not isinstance(commands, list) or not 1 <= len(commands) <= 5
        or any(not isinstance(c, str) or not c.strip() or len(c) > 4000 for c in commands)):
        raise ValueError('verify_commands must contain 1..5 nonempty commands (max 4000 characters each)')


async def check(agent, child, commands):
    record = {'status': 'running', 'checks': []}
    child['acceptance'] = record
    agent.store.save(child)
    try:
        before = agent.memory().fingerprint()
        for command in commands:
            ident = agent.store.begin(child['id'], uuid.uuid4().hex, 'shell', {'command': command})
            try:
                result = await agent.tools.execute('shell', {'command': command})
            except BaseException:
                agent.store.finish(ident, 'Interrupted acceptance; inspect effects before retrying.', 'interrupted')
                raise
            agent.store.finish(ident, result)
            status = command_status(command, result)
            record['checks'].append({'command': command, 'status': status, 'action_id': ident})
            if status != 'passed':
                record['status'] = 'failed'
                return record
        record['status'] = 'passed' if before and agent.memory().fingerprint() == before else 'unconfirmed_snapshot'
        record['fingerprint'] = before
        return record
    finally:
        if record['status'] == 'running':
            record['status'] = 'interrupted'
        agent.store.save(child)
