from aiogram import Router
from handlers.admin import router as admin_router
from handlers.tracking import router as tracking_router
from handlers.start import router as start_router
from handlers.subscription import router as subscription_router
from handlers.referral import router as referral_router
from handlers.payment_callback import router as payment_router


def setup_routers() -> Router:
    main_router = Router()
    main_router.include_router(admin_router)
    main_router.include_router(tracking_router)
    main_router.include_router(start_router)
    main_router.include_router(subscription_router)
    main_router.include_router(referral_router)
    main_router.include_router(payment_router)
    return main_router
