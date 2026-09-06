from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Script
from app.domain.schemas import (
    ScriptCreate,
    ScriptRead,
    ScriptUpdate,
    Stage,
    StageCoverage,
)
from app.domain.templates import KNOWN_PLACEHOLDERS, missing_placeholders
from app.errors import ConflictError, NotFoundError, ValidationFailedError

MAX_VARIANTS_PER_STAGE = 5
STAGES: tuple[Stage, ...] = (1, 2, 3)


class ScriptService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_scripts(self, stage: int | None = None) -> list[ScriptRead]:
        query = select(Script).order_by(Script.stage, Script.variant_index)
        if stage is not None:
            query = query.where(Script.stage == stage)
        rows = await self.session.scalars(query)
        return [ScriptRead.model_validate(row) for row in rows]

    async def get(self, script_id: int) -> ScriptRead:
        return ScriptRead.model_validate(await self._get_or_raise(script_id))

    async def create(self, payload: ScriptCreate) -> ScriptRead:
        self._check_placeholders(payload.template_text)
        await self._ensure_slot_free(payload.stage, payload.variant_index)
        await self._ensure_stage_has_room(payload.stage)

        script = Script(**payload.model_dump())
        self.session.add(script)
        await self.session.commit()
        await self.session.refresh(script)
        return ScriptRead.model_validate(script)

    async def update(self, script_id: int, payload: ScriptUpdate) -> ScriptRead:
        script = await self._get_or_raise(script_id)
        changes = payload.model_dump(exclude_unset=True)

        if "template_text" in changes:
            self._check_placeholders(changes["template_text"])

        stage = changes.get("stage", script.stage)
        variant = changes.get("variant_index", script.variant_index)
        if stage != script.stage or variant != script.variant_index:
            await self._ensure_slot_free(stage, variant, exclude_id=script_id)

        if changes.get("active") is False and script.active:
            await self._ensure_stage_keeps_a_variant(script)

        for field, value in changes.items():
            setattr(script, field, value)

        await self.session.commit()
        await self.session.refresh(script)
        return ScriptRead.model_validate(script)

    async def delete(self, script_id: int) -> None:
        script = await self._get_or_raise(script_id)
        if script.active:
            await self._ensure_stage_keeps_a_variant(script)
        await self.session.delete(script)
        await self.session.commit()

    async def coverage(self) -> list[StageCoverage]:
        rows = list(await self.session.scalars(select(Script)))
        coverage: list[StageCoverage] = []
        for stage in STAGES:
            variants = [row for row in rows if row.stage == stage]
            active = [row for row in variants if row.active]
            coverage.append(
                StageCoverage(
                    stage=stage,
                    variants=len(variants),
                    active_variants=len(active),
                    free_slots=MAX_VARIANTS_PER_STAGE - len(variants),
                    ready=bool(active),
                )
            )
        return coverage

    async def _get_or_raise(self, script_id: int) -> Script:
        script = await self.session.get(Script, script_id)
        if script is None:
            raise NotFoundError(f"script {script_id} not found")
        return script

    def _check_placeholders(self, template_text: str) -> None:
        unknown = missing_placeholders(template_text)
        if unknown:
            known = ", ".join(f"{{{name}}}" for name in KNOWN_PLACEHOLDERS)
            listed = ", ".join(f"{{{name}}}" for name in sorted(unknown))
            raise ValidationFailedError(
                f"unknown placeholders {listed}, only {known} are substituted"
            )

    async def _ensure_slot_free(
        self, stage: int, variant_index: int, exclude_id: int | None = None
    ) -> None:
        query = select(Script.id).where(
            Script.stage == stage, Script.variant_index == variant_index
        )
        if exclude_id is not None:
            query = query.where(Script.id != exclude_id)
        if await self.session.scalar(query) is not None:
            raise ConflictError(f"stage {stage} already has variant {variant_index}")

    async def _ensure_stage_has_room(self, stage: int) -> None:
        used = list(await self.session.scalars(select(Script.id).where(Script.stage == stage)))
        if len(used) >= MAX_VARIANTS_PER_STAGE:
            raise ConflictError(f"stage {stage} already holds {MAX_VARIANTS_PER_STAGE} variants")

    async def _ensure_stage_keeps_a_variant(self, script: Script) -> None:
        siblings = await self.session.scalar(
            select(Script.id)
            .where(
                Script.stage == script.stage,
                Script.id != script.id,
                Script.active.is_(True),
            )
            .limit(1)
        )
        if siblings is None:
            raise ConflictError(f"stage {script.stage} would be left without an active variant")
