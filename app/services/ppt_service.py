from app.schemas.artifacts import PPTArtifact, SlideSchema


class PPTService:
    async def create_from_outline(self, title: str, slides: list[SlideSchema]) -> PPTArtifact:
        raise NotImplementedError

    async def patch_slide(self, ppt_id: str, page_index: int, slide: SlideSchema) -> None:
        raise NotImplementedError
