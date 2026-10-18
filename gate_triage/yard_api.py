"""Cookie-scoped yard API. No planner, model invocation or provider credentials."""
from __future__ import annotations
from typing import Annotated, Literal, Union
import os
import re
import sqlite3

from fastapi import APIRouter, Header, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictStr

from gate_triage.yard_data import PORTS, CARRIERS
from gate_triage.yard_store import YardError

Port = Literal['la', 'rotterdam']
Scenario = Literal['routine', 'power', 'congestion', 'combined']
Issue = Literal['customs', 'weight', 'temperature', 'sensor', 'power', 'congestion']
COOKIE = 'gate_yard_workspace'


class Input(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class Review(Input):
    type: Literal['review']
    containerId: StrictStr = Field(min_length=1, max_length=40)
    issue: Issue
    scenario: Scenario
    choice: Literal['accepted', 'dismissed']
    note: StrictStr = Field(default='', max_length=1000)


class Start(Input):
    type: Literal['start']
    key: StrictStr = Field(min_length=1, max_length=100)


class Complete(Input):
    type: Literal['complete_work']
    key: StrictStr = Field(min_length=1, max_length=100)
    note: StrictStr = Field(min_length=3, max_length=1000)


class Verify(Input):
    type: Literal['verify']
    key: StrictStr = Field(min_length=1, max_length=100)
    evidence: StrictStr = Field(min_length=3, max_length=1000)
    confirmed: StrictBool


class GateOut(Input):
    type: Literal['gate_out']
    containerId: StrictStr = Field(min_length=1, max_length=40)
    scenario: Scenario
    evidence: StrictStr = Field(min_length=3, max_length=1000)
    clearanceConfirmed: StrictBool
    exitConfirmed: StrictBool


class ScenarioChange(Input):
    type: Literal['scenario']
    scenario: Scenario


class Reset(Input):
    type: Literal['reset']


class Observation(Input):
    type: Literal['observe']
    containerId: StrictStr = Field(min_length=1, max_length=40)
    issue: Literal['customs', 'weight', 'temperature', 'sensor']
    note: StrictStr = Field(min_length=3, max_length=1000)


Command = Annotated[Union[Review, Start, Complete, Verify, GateOut, ScenarioChange, Reset, Observation], Field(discriminator='type')]


class LimitedRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()
        async def limited(request):
            data = bytearray()
            async for chunk in request.stream():
                data.extend(chunk)
                if len(data) > 16384: raise HTTPException(413, 'Yard request is too large.')
            request._body = bytes(data)
            return await handler(request)
        return limited


def install_yard(app):
    router = APIRouter(prefix='/api/yard', tags=['Durable yard'], route_class=LimitedRoute)

    @app.exception_handler(YardError)
    async def yard_error(request, error): return JSONResponse({'detail': error.detail}, status_code=error.status)

    def store(request): return request.app.state.yard_store
    def token(request): return request.cookies.get(COOKIE)
    def browser_write(request):
        if request.headers.get('X-Yard-Request') != '1': raise HTTPException(400, 'The yard request header is required.')

    def protect_db(fn, *args):
        try: return fn(*args)
        except sqlite3.Error: raise HTTPException(503, 'Yard database temporarily unavailable. Retry the same request.') from None

    @router.post('/session')
    def session(request: Request, response: Response):
        browser_write(request)
        value, data = protect_db(store(request).session, token(request))
        response.set_cookie(COOKIE, value, httponly=True, samesite='strict', secure=request.url.scheme == 'https' or bool(os.getenv('RENDER')), max_age=604800, path='/api/yard')
        return data

    @router.get('/health')
    def health(request: Request):
        def check():
            with store(request).connection() as db: db.execute('SELECT 1').fetchone()
        protect_db(check)
        return dict(status='ok', database='sqlite', storage='filesystem', persisted=True, synthetic=True, agentEnabled=False)

    @router.get('/ports')
    def ports():
        return dict(ports=[dict(code=p, name=v['name'], locale=v['locale'], timeZone=v['timeZone'], blocks=12 if p == 'la' else 8) for p, v in PORTS.items()], synthetic=True)

    @router.get('/ports/{port}/snapshot')
    def snapshot(port: Port, request: Request, if_none_match: str | None = Header(default=None)):
        data, etag = protect_db(store(request).snapshot, token(request), port, if_none_match)
        return Response(status_code=304, headers={'ETag': etag}) if data is None else JSONResponse(data, headers={'ETag': etag})

    @router.post('/ports/{port}/commands')
    def command(port: Port, event: Command, request: Request, if_match: str | None = Header(default=None), idempotency_key: str | None = Header(default=None)):
        browser_write(request)
        if not if_match: raise HTTPException(428, 'Load the current yard version before changing it.')
        if not idempotency_key or not re.fullmatch(r'[a-zA-Z0-9_-]{8,128}', idempotency_key): raise HTTPException(400, 'A valid Idempotency-Key is required.')
        data, etag = protect_db(store(request).command, token(request), port, event.model_dump(), if_match, idempotency_key)
        return JSONResponse(data, headers={'ETag': etag})

    @router.get('/ports/{port}/containers')
    def containers(port: Port, request: Request, container_id: str = Query(default='', max_length=80), company: str = Query(default='', max_length=100), block: str = Query(default='', max_length=10), exceptions_only: bool = False, offset: int = Query(default=0, ge=0, le=10000), limit: int = Query(default=100, ge=1, le=200)):
        data, _ = protect_db(store(request).snapshot, token(request), port)
        container_id, block = container_id.strip(), block.strip().upper()
        normalize = lambda text: re.sub('[^A-Z0-9]', '', text.upper())
        company_key = re.sub(r'[\s-]+', '', company.lower())
        rows = [c for c in data['catalog'] if c['yardStatus'] == 'in-yard'
                and (not container_id or bool(normalize(container_id)) and normalize(container_id) in c['id'])
                and (not company_key or company_key in re.sub(r'[\s-]+', '', f"{c['carrier']} {CARRIERS[c['carrier']]}".lower()))
                and (not block or c['block'] == block)
                and (not exceptions_only or c['assessments'][data['scenario']])]
        return dict(items=rows[offset:offset + limit], total=len(rows), offset=offset, limit=limit, revision=data['revision'], runId=data['runId'])

    @router.get('/ports/{port}/containers/{container_id}')
    def container(port: Port, container_id: str, request: Request):
        data, _ = protect_db(store(request).snapshot, token(request), port)
        c = next((c for c in data['catalog'] if c['id'] == container_id), None)
        if not c: raise HTTPException(404, 'Container not found in this yard run.')
        with store(request).connection() as db:
            original = db.execute('SELECT original_data FROM yard_containers WHERE run=? AND id=?', (data['runId'], container_id)).fetchone()
        import json
        return dict(container=c, originalObservation=json.loads(original[0]), revision=data['revision'], synthetic=True)

    @router.get('/ports/{port}/audit')
    def audit(port: Port, request: Request, limit: int = Query(default=100, ge=1, le=500)):
        return dict(events=protect_db(store(request).audit, token(request), port, limit))

    app.include_router(router)
