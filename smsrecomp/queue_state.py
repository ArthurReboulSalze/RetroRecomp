"""Small local batch checkpoints, recovered explicitly through Convert.

ROMs and executables are never copied here. The definition is written once;
completed row numbers are checkpointed separately. An OS lock distinguishes
an interrupted run from another converter instance still doing useful work.
"""
from dataclasses import asdict
import json
import os
from pathlib import Path
import re
import uuid

from .library import atomic_json
from .platforms import target_id

MAX_BYTES = 16 * 1024 * 1024
MAX_ITEMS = 8192


def _read(path):
    with path.open('rb') as stream:
        raw = stream.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError('Batch recovery file exceeds its size limit.')
    return json.loads(raw)


def _lock(path):
    stream = path.open('a+b')
    try:
        if os.name == 'nt':
            import msvcrt
            stream.seek(0);msvcrt.locking(stream.fileno(),msvcrt.LK_NBLCK,1)
        else:
            import fcntl
            fcntl.flock(stream,fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BaseException:
        stream.close();raise
    return stream


class BatchJournal:
    def __init__(self, path, stream, definition, done=None):
        self.path,self.stream,self.definition=path,stream,definition
        self.done=dict(done or {})

    @classmethod
    def create(cls, directory, items, output):
        if not 1 <= len(items) <= MAX_ITEMS:
            raise ValueError('Batch recovery supports 1–8192 rows.')
        directory.mkdir(parents=True,exist_ok=True)
        rows=[]
        for item in items:
            row=asdict(item)
            row.update(path=str(item.path),cover=str(item.cover) if item.cover else None)
            rows.append(row)
        definition={'schema':1,'target':target_id(),'output':str(output.resolve()),'items':rows}
        if len(json.dumps(definition).encode('utf-8')) > MAX_BYTES:
            raise ValueError('Batch recovery file exceeds its size limit.')
        path=directory/(uuid.uuid4().hex+'.json');stream=_lock(path.with_suffix('.lock'))
        try:
            atomic_json(path,definition)
            journal=cls(path,stream,definition);journal.save(False);return journal
        except BaseException:
            stream.close();raise

    @property
    def progress(self):
        return self.path.with_suffix('.progress.json')

    def save(self, finished):
        atomic_json(self.progress,{'schema':1,'finished':bool(finished),'done':self.done})

    def result(self, index, value):
        if type(index) is not int or not 0 <= index < len(self.definition['items']):
            raise ValueError('Invalid batch recovery row.')
        self.done[str(index)]=value['status'];self.save(False)

    def finish(self, record):
        try:self.save(record.get('pending',0)==0)
        finally:self.close()

    def discard(self):
        try:self.save(True)
        finally:self.close()

    def close(self):
        if self.stream is not None:
            self.stream.close();self.stream=None

    def pending_items(self):
        from .batch import BatchItem
        result=[]
        for index,row in enumerate(self.definition['items']):
            if str(index) in self.done:continue
            values={**row,'path':Path(row['path']),'cover':Path(row['cover']) if row['cover'] else None}
            result.append(BatchItem(**values))
        return result


def recover(directory):
    """Reserve the newest interrupted queue; never open or identify a ROM."""
    try:
        candidates=[p for p in directory.glob('*.json') if not p.name.endswith('.progress.json')]
        if not candidates:return None
        candidates.sort(key=lambda p:p.stat().st_mtime_ns,reverse=True)
    except OSError:
        return None
    for path in candidates:
        journal=_recover_path(path)
        if journal is not None:return journal
    return None


def _recover_path(path):
    stream=None
    try:
        stream=_lock(path.with_suffix('.lock'))
        definition=_read(path);checkpoint=_read(path.with_suffix('.progress.json'))
        if (definition['schema']!=1 or definition['target']!=target_id()
                or checkpoint['schema']!=1 or type(checkpoint['finished']) is not bool
                or checkpoint['finished'] or not Path(definition['output']).is_absolute()
                or not isinstance(definition['items'],list) or not 1<=len(definition['items'])<=MAX_ITEMS
                or not isinstance(checkpoint['done'],dict)):
            stream.close();return None
        from .batch import BatchItem
        fields=set(BatchItem.__dataclass_fields__)
        for row in definition['items']:
            if (not isinstance(row,dict) or set(row)!=fields or not isinstance(row['path'],str)
                    or not Path(row['path']).is_absolute()
                    or not isinstance(row['title'],str) or not isinstance(row['system'],str)
                    or row['system'] not in ('sms','gg','gb','nes','md','snes','ng','')
                    or not isinstance(row['sha256'],str)
                    or row['sha256'] and not re.fullmatch('[0-9a-f]{64}',row['sha256'])
                    or row['cover'] is not None and not isinstance(row['cover'],str)):
                raise ValueError('Invalid batch recovery item.')
        for index,status in checkpoint['done'].items():
            if (not isinstance(index,str) or not index.isdecimal() or not 0<=int(index)<len(definition['items'])
                    or not isinstance(status,str)):
                raise ValueError('Invalid batch recovery checkpoint.')
        journal=BatchJournal(path,stream,definition,checkpoint['done'])
        if not journal.pending_items():journal.close();return None
        return journal
    except (OSError,ValueError,KeyError,TypeError,AttributeError):
        if stream is not None:stream.close()
        return None
