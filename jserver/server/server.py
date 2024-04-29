from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from jserver.config import Config

from .input_handler_router import router as input_handler_router
from .output_router import router as output_router

from jserver.utils.logger import setup_logging
logger = setup_logging(__name__)

app = FastAPI()

app.include_router(input_handler_router, prefix="/input_handlers")
app.include_router(output_router, prefix="/output")

@app.get("/ping")
async def ping():
    return JSONResponse(status_code=200, content={"message": "pong"})

@app.get("/")
async def root():
    return JSONResponse(status_code=200, content={"message": "Hello World"})

class AsyncServer:
    def __init__(self, config: Config):
        from uvicorn import Config as ServerConfig
        from uvicorn import Server
        cors = config.output_config.cors
        port = config.output_config.port
        host = config.output_config.host
        if cors is not None:
            logger.warning(f"Using CORS: {cors}")
            app.add_middleware(
                CORSMiddleware,
                allow_origins=cors,
            )
        self.config = ServerConfig(app=app, host=host, port=port, loop="none")
        self.server = Server(config=self.config)

    async def start(self):
        await self.server.serve()

    async def stop(self):
        self.server.should_exit = True

async def start_server(config: Config):
    server = AsyncServer(config)
    await server.start()
