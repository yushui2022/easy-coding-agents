"""Transport-independent task lifecycle shared by the CLI and desktop."""
import asyncio
from dataclasses import replace

from .agent import Agent
from .workflow import verified_run, validate_checks


class Runtime:
    def __init__(self, agent):
        self.agent = agent
        self.task = None

    @property
    def busy(self):
        return self.task is not None and not self.task.done()

    def idle(self):
        if self.busy or self.agent.busy:
            raise ValueError('A task is running; stop it before switching or modifying this session.')

    def start(self, prompt, commands=(), repair_attempts=0, worker_first=None):
        self.idle()
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError('Enter a nonempty task.')
        validate_checks(self.agent, commands, repair_attempts)
        self.task = asyncio.create_task(verified_run(self.agent, prompt, list(commands), repair_attempts, worker_first))
        return self.task

    def cancel(self):
        if self.busy and not self.task.cancelling():
            self.task.cancel()

    async def switch(self, identifier=None, base_settings=None, restore_model_profile=True):
        self.idle()
        old = self.agent
        state = old.store.load(identifier) if identifier else old.store.create(old.settings.mode)
        base = base_settings or old.settings
        settings = base.select_profile(state['model_profile']) if restore_model_profile and state.get('model_profile') else replace(base)
        settings.mode = state['mode']
        if state.get('sandbox'):
            settings.sandbox = state['sandbox']
            settings.sandbox_image = state.get('sandbox_image', settings.sandbox_image)
        settings.validate()
        await old.close()
        self.agent = Agent(settings, old.store, state, old.tools.approve, old.tools.question, old.emit,
                           child=bool(state.get('parent_id')))
        state.update(sandbox=settings.sandbox, sandbox_image=settings.sandbox_image)
        if settings.model_profile:
            state['model_profile'] = settings.model_profile
        old.store.save(state)
        return self.agent

    async def close(self):
        self.cancel()
        if self.task is not None:
            await asyncio.gather(self.task, return_exceptions=True)
        try:
            await self.agent.close()
        finally:
            self.agent.store.close()
