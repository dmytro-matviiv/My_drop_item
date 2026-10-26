from aiogram import Router

from . import search, start, vendors


def build_router() -> Router:
    router = Router()
    # порядок важливий: пошук за артикулом ловить увесь інший текст
    router.include_routers(start.router, vendors.router, search.router)
    return router
