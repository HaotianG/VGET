"""JSON command-line interface. No server or provider-specific model required."""
import argparse
import json
import os
from pathlib import Path
import sys
from .contracts import TOOL_LIST, ToolError
from .toolkit import Toolkit

class Parser(argparse.ArgumentParser):
    def error(self,message):raise ToolError('CLI_USAGE',message)

def emit(tool,data=None,error=None):
    response={'schema_version':'0.2.0','tool':tool,'status':'error' if error else 'ok'}
    if error:response['error']={'code':error.code,'message':str(error),'details':error.details}
    else:
        response['data']=data
        if data.get('job',{}).get('status') in ('needs_input','infeasible'):response['status']='needs_input'
        if data.get('job',{}).get('status')=='unsupported':response['status']='unsupported'
    print(json.dumps(response,ensure_ascii=False,allow_nan=False))

def read_input(path):
    try:
        if path=='-':text=sys.stdin.read(1024*1024+1)
        else:
            file=Path(path).expanduser()
            if file.stat().st_size>1024*1024:raise ToolError('INPUT_LIMIT','Tool arguments must be at most 1 MB.')
            text=file.read_text()
        if len(text.encode())>1024*1024:raise ToolError('INPUT_LIMIT','Tool arguments must be at most 1 MB.')
        def pairs(items):
            result={}
            for key,value in items:
                if key in result:raise ValueError('Duplicate JSON key: '+key)
                result[key]=value
            return result
        def invalid(token):raise ValueError('Non-finite JSON value: '+token)
        return json.loads(text,object_pairs_hook=pairs,parse_constant=invalid)
    except ToolError:raise
    except (OSError,UnicodeError,ValueError) as e:raise ToolError('INPUT_JSON',f'Cannot read JSON arguments: {e}') from e

def main(argv=None):
    tool='cli'
    try:
        parser=Parser(prog='vget',description='VGET agent toolkit: objective → reasoned plan → annotated GenBank and HTML. The calling agent supplies reasoning.')
        parser.add_argument('--workspace',default=os.environ.get('VGET_DATA_DIR','.vget'),help='Local data directory, shared with optional GUI')
        sub=parser.add_subparsers(dest='command',required=True)
        sub.add_parser('tools',help='Print all tool descriptions and JSON input schemas')
        call=sub.add_parser('call',help='Invoke a tool without a web server');call.add_argument('tool');call.add_argument('--input',default='-',help='JSON file or - for stdin')
        init=sub.add_parser('init',help='Initialize workspace with six real iGEM reference records');group=init.add_mutually_exclusive_group();group.add_argument('--demo',action='store_true',help='Add synthetic demo records instead');group.add_argument('--empty',action='store_true',help='Start without installed records')
        serve=sub.add_parser('serve',help='Optional manual GUI for the same workspace');serve.add_argument('--port',type=int,default=8766)
        args=parser.parse_args(argv)
        if args.command=='tools':emit('tools',{'tools':TOOL_LIST,'integration':'Call through CLI or Toolkit.call. This is not an MCP transport.'});return 0
        if args.command=='serve':
            from .app import create_app
            # GUI does not silently seed agent workspaces.
            Toolkit(args.workspace)
            app=create_app(args.workspace)
            print(f'VGET optional manual workspace: http://127.0.0.1:{args.port}',file=sys.stderr)
            app.run(host='127.0.0.1',port=args.port,debug=False,use_reloader=False)
            return 0
        tool='workspace.init' if args.command=='init' else args.tool
        arguments={'demo':args.demo,'empty':args.empty} if args.command=='init' else read_input(args.input)
        result=Toolkit(args.workspace).call(tool,arguments)
        emit(tool,result);return 0
    except ToolError as e:emit(tool,error=e);return 2
    except (OSError,TimeoutError) as e:emit(tool,error=ToolError('WORKSPACE_IO',str(e)));return 2
    except Exception as e:emit(tool,error=ToolError('INTERNAL_ERROR','Unexpected local toolkit failure.',type(e).__name__));return 3

if __name__=='__main__':raise SystemExit(main())
