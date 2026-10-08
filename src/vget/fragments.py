"""Explicit source-range preparation with complete feature accounting.

This is coordinate bookkeeping, not a prediction of physical cutting or PCR.
The original record stays immutable; no intermediate enters the library.
"""
from __future__ import annotations
import copy
from Bio.Seq import Seq
from Bio.SeqFeature import CompoundLocation, SimpleLocation
from .contracts import FRAGMENT, ToolError, validate
from .sequence import (SequenceError, _finalize, _hash, _location, _location_text,
                       _require_exact, _require_transformable, _segments)


def _ranges(record, spec):
    try: validate(spec, FRAGMENT, 'fragment')
    except ToolError as error:
        raise SequenceError('FRAGMENT_SPEC', str(error), error.details) from error
    if spec['record_id'] != record['id']:
        raise SequenceError('FRAGMENT_SPEC', 'Fragment record_id must identify the supplied original record.')
    ranges = spec['ranges']; size = record['length']
    if record['topology'] not in ('linear', 'circular'):
        raise SequenceError('FRAGMENT_RANGES', 'Declare known linear or circular source topology before preparation.')
    if not 1 <= len(ranges) <= 2 or any(not 0 <= r['start'] < r['end'] <= size for r in ranges):
        raise SequenceError('FRAGMENT_RANGES', 'Supply one or two nonempty ranges within the exact source length.')
    if len(ranges) == 2 and not (record['topology'] == 'circular' and
            ranges[0]['end'] == size and ranges[1]['start'] == 0 and
            ranges[1]['end'] < ranges[0]['start']):
        raise SequenceError('FRAGMENT_RANGES', 'Two ranges must follow one circular origin crossing: [start,length), [0,end), with end < start. No gaps, repetition or full-circle rotation.')
    if sum(r['end'] - r['start'] for r in ranges) > 10000:
        raise SequenceError('FRAGMENT_LIMIT', 'A prepared fragment must contain at most 10,000 bases.')
    return ranges


def _project(location, ranges, size, reverse):
    """Intersect exact source locations, retaining biological part order."""
    _require_exact(location)
    if any(int(p.start)==int(p.end) for p in location.parts):
        raise SequenceError('FRAGMENT_POINT_LOCATION','Point/between-base locations require a reviewed boundary map; they cannot be silently excluded.')
    offsets=[]; offset=0
    for r in ranges:
        offsets.append(offset); offset += r['end'] - r['start']
    parts=[]; covered=0
    for p in location.parts:
        intersections=[]
        for r, offset in zip(ranges, offsets):
            start=max(int(p.start), r['start']); end=min(int(p.end), r['end'])
            if start < end:
                covered += end - start
                intersections.append((start, SimpleLocation(offset+start-r['start'], offset+end-r['start'], strand=p.strand)))
        intersections.sort(key=lambda item:item[0], reverse=p.strand == -1)
        parts.extend(part for _,part in intersections)
    if reverse:
        parts=[SimpleLocation(size-int(p.end),size-int(p.start),strand=-p.strand if p.strand in (-1,1) else p.strand) for p in parts]
    # Adjacent segments of one join can become one span after origin selection.
    # This preserves extracted sequence and is recorded in the comparison.
    merged=[]
    for p in parts:
        old=merged[-1] if merged else None
        adjacent=old and old.strand == p.strand and (
            (p.strand == -1 and int(p.end) == int(old.start)) or
            (p.strand != -1 and int(old.end) == int(p.start)))
        if adjacent:
            merged[-1]=SimpleLocation(min(int(old.start),int(p.start)),max(int(old.end),int(p.end)),strand=p.strand)
        else: merged.append(p)
    mapped=None if not merged else merged[0] if len(merged)==1 else CompoundLocation(merged,'join')
    return mapped, covered, sum(int(p.end)-int(p.start) for p in location.parts)


def prepare_fragment(record, spec):
    ranges=_ranges(record,spec)
    _require_transformable(record)
    reverse=spec['orientation'] == 'reverse'
    sequence=''.join(record['sequence'][r['start']:r['end']] for r in ranges)
    if reverse: sequence=str(Seq(sequence).reverse_complement())
    size=len(sequence); features=[]; comparisons=[]; partial=False; unstranded=False
    for feature in record['features']:
        location=_location(feature['location'],record['length'],record['topology'])
        mapped,covered,total=_project(location,ranges,size,reverse)
        whole_source=feature['type']=='source' and len(location.parts)==1 and int(location.start)==0 and int(location.end)==record['length']
        status='excluded' if covered==0 else 'retained' if covered==total else 'projected_source' if whole_source else 'partial'
        if status=='projected_source':
            strand=location.strand
            mapped=SimpleLocation(0,size,strand=-strand if reverse and strand in (-1,1) else strand)
        comparison={'source_feature_id':feature['id'],'label':feature['label'],'type':feature['type'],
                    'source_location':feature['location'],'status':status,'source_bases':total,'selected_bases':covered,
                    'fragment_location':_location_text(mapped,size) if mapped else None}
        comparisons.append(comparison)
        if status=='partial': partial=True
        if status not in ('retained','projected_source'): continue
        if reverse and any(p.strand not in (-1,1) for p in location.parts): unstranded=True
        f=copy.deepcopy(feature)
        origin={'source_id':record['id'],'source_feature_id':feature['id'],'source_location':feature['location'],
                'ranges':copy.deepcopy(ranges),'orientation':spec['orientation'],'outcome':status}
        if feature.get('provenance'): origin['prior_provenance']=copy.deepcopy(feature['provenance'])
        f.update(id='feat-'+_hash(['fragment',spec,feature['id']])[:20],location=_location_text(mapped,size),
                 segments=_segments(mapped),provenance=origin)
        features.append(f)
    report={'source_id':record['id'],'source_name':record['name'],'source_length':record['length'],
            'source_sequence_sha256':record['sequence_sha256'],'ranges':copy.deepcopy(ranges),'orientation':spec['orientation'],
            'coordinate_system':'0-based half-open','fragment_length':size,'fragment_sequence_sha256':_hash(sequence),
            'features':comparisons,'references':[],
            'limitations':['Exact coordinate selection only; no physical cutting, primers or reaction validation.',
                           'Partial features are rejected except audited projection of a single whole-record source annotation; outside features are explicitly excluded.',
                           'Bibliography text is retained; reference ranges are explicitly projected onto selected bases.']}
    if partial:
        raise SequenceError('FRAGMENT_PARTIAL_FEATURE','A selected boundary cuts through an annotation; resolve the ranges rather than clipping it.',report)
    if unstranded:
        raise SequenceError('FRAGMENT_STRAND','Reverse preparation requires explicit + or - strand on every retained feature; unknown strands need review.',report)
    references=copy.deepcopy(record.get('metadata',{}).get('annotations',{}).get('references',[]))
    for index,ref in enumerate(references):
        projected=[]; total=covered=0
        for text in ref.get('location',[]):
            mapped,bases,original=_project(_location(text,record['length'],record['topology']),ranges,size,reverse)
            total+=original; covered+=bases
            if mapped: projected.append(_location_text(mapped,size))
        report['references'].append({'index':index,'source_locations':copy.deepcopy(ref.get('location',[])),
            'fragment_locations':projected,'status':'unlocalized' if total==0 else 'outside' if covered==0 else 'retained' if covered==total else 'projected'})
        ref['location']=projected
    name='fragment_'+_hash(spec)[:12]
    fragment=_finalize({'name':name,'description':'Explicit source-range preparation; physical preparation unevaluated.',
        'sequence':sequence,'topology':'linear','features':features,
        'metadata':{'record_id':name,'record_name':name,'annotations':{'molecule_type':'DNA','topology':'linear','references':references},
                    'dbxrefs':copy.deepcopy(record.get('metadata',{}).get('dbxrefs',[])),
                    'fragment_preparation':copy.deepcopy(report)},
        'source':{'kind':'fragment_preparation','original_record_id':record['id']}})
    report['fragment_id']=fragment['id']
    return fragment,report


def prepare_fragments(records, specs):
    if not isinstance(specs,list) or len(specs)!=2 or len(records)!=2:
        raise SequenceError('FRAGMENT_SPEC','This workflow prepares exactly two fragments in backbone, insert order.')
    values=[prepare_fragment(record,spec) for record,spec in zip(records,specs)]
    return [v[0] for v in values],[v[1] for v in values]
