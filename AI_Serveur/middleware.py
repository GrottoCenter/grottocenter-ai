import json

# Multipart framing (boundaries, part headers, the file name) on top of the file itself.
MULTIPART_OVERHEAD_BYTES = 1024 * 1024


class MaxBodySizeMiddleware:
    """Refuse an oversized upload before the application reads it.

    FastAPI parses the whole multipart body before any route code runs, so a limit
    inside the route could only fire after the upload had been received and spooled.
    This limit is deliberately a little above the file limit (multipart overhead); the
    exact file size is checked by DocumentService, which is also what keeps a file that
    is only slightly too big from being analysed.
    """

    def __init__(self, app, max_file_bytes: int, path: str, method: str = "POST") -> None:
        self.app = app
        self.max_body_bytes = max_file_bytes + MULTIPART_OVERHEAD_BYTES
        self.path = path
        self.method = method

    async def __call__(self, scope, receive, send):
        if (
            scope["type"] != "http"
            or scope["path"] != self.path
            or scope["method"] != self.method
        ):
            await self.app(scope, receive, send)
            return

        declared = dict(scope["headers"]).get(b"content-length")
        if declared is not None and declared.isdigit() and int(declared) > self.max_body_bytes:
            await self._refuse(send)
            return

        received = 0
        refused = False
        response_started = False

        async def counting_receive():
            nonlocal received, refused
            if refused:
                return {"type": "http.disconnect"}
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_body_bytes and not response_started:
                    # FastAPI turns any error raised while it reads the body into a
                    # generic 400, so the 413 is sent from here, and the application is
                    # told the client went away so that it stops reading.
                    refused = True
                    await self._refuse(send)
                    return {"type": "http.disconnect"}
            return message

        async def guarded_send(message):
            nonlocal response_started
            if refused:
                return  # already answered with 413; drop whatever the application says
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        await self.app(scope, counting_receive, guarded_send)

    async def _refuse(self, send) -> None:
        limit_mb = (self.max_body_bytes - MULTIPART_OVERHEAD_BYTES) // (1024 * 1024)
        body = json.dumps(
            {"detail": f"File too large: the limit is {limit_mb} MB"}
        ).encode()
        await send(
            {
                "type": "http.response.start",
                "status": 413,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                    (b"connection", b"close"),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})
