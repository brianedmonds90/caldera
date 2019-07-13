import json
import re
from base64 import b64decode
from datetime import datetime


class ParsingService:

    def __init__(self, data_svc):
        self.data_svc = data_svc

    async def parse_facts(self, operation):
        sql = 'SELECT b.id, b.ability, a.output, a.link_id FROM core_result a inner join core_chain b on a.link_id=b.id ' \
              'where b.op_id = %s and a.parsed is null;' % operation['id']
        op_source = await self.data_svc.dao.get('core_source', dict(name=operation['name']))
        for x in await self.data_svc.dao.raw_select(sql):
            parsers = await self.data_svc.dao.get('core_parser', dict(ability=x['ability']))
            if parsers:
                for parser in parsers:
                    if parser['name'] == 'json':
                        matched_facts = self._json(parser, b64decode(x['output']).decode('utf-8'))
                    elif parser['name'] == 'line':
                        matched_facts = self._line(parser, b64decode(x['output']).decode('utf-8'))
                    elif parser['name'] == 'split':
                        matched_facts = self._split(parser, b64decode(x['output']).decode('utf-8'))
                    else:
                        matched_facts = self._regex(parser, b64decode(x['output']).decode('utf-8'))

                    # save facts to DB
                    for match in matched_facts:
                        if not any(f['property'] == match['fact'] and f['value'] == match['value'] and f['blacklist'] for f in
                                   operation['facts']):
                            await self.data_svc.create_fact(
                                source_id=op_source[0]['id'], link_id=x['id'], property=match['fact'], value=match['value'],
                                set_id=match['set_id'], score=1, blacklist=0
                            )

                # mark result as parsed
                update = dict(parsed=datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
                await self.data_svc.dao.update('core_result', key='link_id', value=x['link_id'], data=update)

    """ PRIVATE """

    @staticmethod
    def _json(parser, blob):
        matched_facts = []
        if blob:
            structured = json.loads(blob)
            if isinstance(structured, (list,)):
                for i, entry in enumerate(structured):
                    matched_facts.append((dict(fact=parser['property'], value=entry.get(parser['script']), set_id=i)))
            elif isinstance(structured, (dict,)):
                dict_match = parser['script']
                dict_match = dict_match.split(',')
                match = structured
                for d in dict_match:
                    match = match[d]
                matched_facts.append((dict(fact=parser['property'],value = match,set_id=0)))
            else:
                matched_facts.append((dict(fact=parser['property'], value =structured[parser['script']],set_id=0)))
        return matched_facts

    @staticmethod
    def _regex(parser, blob):
        matched_facts = []
        for i, v in enumerate([m for m in re.findall(parser['script'], blob)]):
            matched_facts.append(dict(fact=parser['property'], value=v, set_id=i))
        return matched_facts

    @staticmethod
    def _line(parser, blob):
        return [dict(fact=parser['property'], value=f, set_id=0) for f in blob.split('\n') if f]

    @staticmethod
    def _split(parser, blob):
        split_val = parser['script'].split(',')[1]
        split_pos = int(parser['script'].split(',')[0])
        matched_facts = []
        for i, f in enumerate(blob.split('\n')):
            if f:
                matched_facts.append(dict(fact=parser['property'], value=f.split(split_val)[split_pos], set_id=i))
        return matched_facts

