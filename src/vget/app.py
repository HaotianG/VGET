"""Loopback-only local VGET application. No cloud model or source scraping."""
from __future__ import annotations
import os
from pathlib import Path
from urllib.parse import urlparse

from flask import Flask, jsonify, request, send_file, send_from_directory
from werkzeug.exceptions import HTTPException
from .store import Store, HOSTS
from .sequence import SequenceError
from .conventions import ConventionError
from .service import APIError, Service, SOURCES, LIMITATIONS, validate_payload


def _payload():
    return validate_payload(request.get_json(silent=True))


def create_app(data_dir=None,testing=False):
    root=Path(data_dir or os.environ.get('VGET_DATA_DIR',Path.cwd()/'.vget'))
    app=Flask(__name__,static_folder='static',static_url_path='/static')
    app.config.update(TESTING=testing,DATA_DIR=str(root.resolve()),MAX_CONTENT_LENGTH=12*1024*1024)
    store=Store(root);service=Service(store)
    app.extensions['vget_store']=store;app.extensions['vget_service']=service

    @app.before_request
    def local_boundary():
        host=urlparse('http://'+request.host).hostname
        if host not in ('localhost','127.0.0.1','::1'):raise APIError('LOCAL_ONLY','This prototype accepts loopback hostnames only.',403)
        if request.method not in ('GET','HEAD','OPTIONS'):
            if request.headers.get('X-VGET-Local')!='1':raise APIError('LOCAL_REQUEST_REQUIRED','Use the local interface or include X-VGET-Local: 1.',403)
            origin=request.headers.get('Origin')
            if origin and origin!=request.host_url.rstrip('/'):
                raise APIError('CROSS_ORIGIN_DENIED','Cross-origin writes are disabled.',403)

    @app.after_request
    def response_headers(response):
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['Referrer-Policy']='no-referrer'
        response.headers['X-Frame-Options']='DENY'
        response.headers['Cache-Control']='no-store'
        response.headers['Content-Security-Policy']="default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'"
        return response

    @app.errorhandler(APIError)
    def api_error(e):return jsonify(error={'code':e.code,'message':str(e),'details':e.details}),e.status
    @app.errorhandler(SequenceError)
    def sequence_error(e):return jsonify(error={'code':e.code,'message':str(e),'details':e.details}),422
    @app.errorhandler(ConventionError)
    def convention_error(e):return jsonify(error={'code':'CONVENTION_INVALID','message':str(e)}),422
    @app.errorhandler(HTTPException)
    def http_error(e):return jsonify(error={'code':e.name.upper().replace(' ','_'),'message':e.description}),e.code

    @app.get('/')
    def index():return send_from_directory(app.static_folder,'index.html')
    @app.get('/api/state')
    def state_api():
        state=store.load()
        return jsonify(records=list(state['records'].values()),designs=list(reversed(list(state['designs'].values()))),hosts=HOSTS,conventions=list(state['conventions'].values()),sources=SOURCES,limitations=LIMITATIONS)

    @app.post('/api/import')
    def import_api():
        items=[(file.filename or '',file.read()) for file in request.files.getlist('files')]
        return jsonify(service.import_files(items,request.form.get('source','lab'))),201

    @app.post('/api/brief')
    def brief_api():
        return jsonify(service.brief(_payload()))

    @app.post('/api/conventions')
    def conventions_api():
        payload=_payload()
        return jsonify(convention=service.draft_convention(payload.get('name'),payload.get('notes'))),201

    @app.post('/api/conventions/<cid>/activate')
    def activate_api(cid):
        return jsonify(convention=service.activate_convention(cid,_payload().get('reviewed')))

    @app.post('/api/compare')
    def compare_api():
        payload=_payload()
        return jsonify(comparison=service.compare(payload.get('left_id'),payload.get('right_id')))

    @app.post('/api/design')
    def design_api():
        return jsonify(design=service.design(_payload())),201

    @app.get('/api/designs/<did>')
    def design_get(did):
        d=store.load()['designs'].get(did)
        if not d:raise APIError('DESIGN_NOT_FOUND','Design not found.',404)
        return jsonify(design=d)

    @app.get('/api/designs/<did>/<filename>')
    def artifact_get(did,filename):
        if did not in store.load()['designs'] or filename not in ('construct.gbk','report.html','bundle.zip'):raise APIError('ARTIFACT_NOT_FOUND','Artifact not found.',404)
        path=store.packages/did/filename
        if not path.is_file():raise APIError('ARTIFACT_MISSING','Stored artifact is missing. The original design remains recorded.',409)
        return send_file(path,mimetype={'construct.gbk':'text/plain','report.html':'text/html','bundle.zip':'application/zip'}[filename],as_attachment=filename!='report.html',download_name=filename)
    return app
