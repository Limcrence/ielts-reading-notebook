"""Convert school reading reports into notebook articles, exercises and questions."""
import hashlib
import html
import json
import re


def parse(value):
    if not isinstance(value, str):
        return value if value is not None else {}
    try:
        return json.loads(value)
    except (ValueError, TypeError):
        return value


def clean(text):
    text = html.unescape(str(text or '')).replace('\xa0', ' ')
    text = re.sub(r'<[^>]+>', ' ', text)
    return '\n'.join(re.sub(r'[ \t]+', ' ', line).strip() for line in text.splitlines() if line.strip()).strip()


def rich(node, target=None):
    node = parse(node)
    if isinstance(node, str):
        return clean(node)
    if isinstance(node, (int,float)):
        return str(node)
    if isinstance(node, list):
        return ''.join(rich(x, target) for x in node)
    if not isinstance(node, dict):
        return ''
    typ = node.get('type', '')
    if typ == 'text':
        return node.get('text', '')
    if typ in {'serialNumberNode', 'DraggableInputNode', 'fillBlank', 'input'}:
        attrs = node.get('attrs', {})
        idx = attrs.get('index', attrs.get('subIndex'))
        number = attrs.get('text') or attrs.get('label') or '?'
        return ' [本题____] ' if target is not None and idx == target else f' [{number}] '
    if typ == 'hardBreak':
        return '\n'
    if typ in {'CustomImageNode', 'image'}:
        return '[题图]'
    if 'cellMatrix' in node:
        return '\n'.join(' | '.join(rich(c.get('content'), target) for c in row.get('cells', [])) for row in node['cellMatrix'])
    content = node.get('content', [])
    text = rich(content, target)
    if typ in {'paragraph', 'heading', 'listItem', 'tableRow', 'nonEditableBlock'}:
        text += '\n'
    return text


def walk(node):
    node = parse(node)
    if isinstance(node, dict):
        yield node
        for val in node.values():
            if isinstance(val, (dict, list)):
                yield from walk(val)
            elif isinstance(val, str) and val.startswith('{'):
                yield from walk(parse(val))
    elif isinstance(node, list):
        for child in node:
            yield from walk(child)


def markers(doc):
    return [n for n in walk(doc) if n.get('type') in {'serialNumberNode', 'DraggableInputNode'}]


def image_urls(doc):
    return list(dict.fromkeys(n.get('attrs', {}).get('src') for n in walk(doc) if n.get('type') in {'CustomImageNode', 'image'} and n.get('attrs', {}).get('src')))


def flatten_answer(value):
    obj = parse(value)
    if not obj or not isinstance(obj, dict):
        return []
    result = obj.get('answers', {}).get('answer', [])
    if result is None:
        return []
    if not isinstance(result, list):
        result = [result]
    def flat(x):
        if isinstance(x, list):
            return [v for item in x for v in flat(item)]
        return [str(x)] if str(x or '').strip() else []
    return flat(result)


def options(body):
    if body.get('choices'):
        return {chr(65+i): clean(rich(x.get('content', x))) for i, x in enumerate(body['choices'])}
    if body.get('options'):
        opts = body['options']
        if isinstance(opts, dict):
            return {str(k): clean(rich(v)) for k,v in opts.items()}
        return {chr(65+i): clean(rich(x.get('content', x) if isinstance(x,dict) else x)) for i,x in enumerate(opts)}
    table = body.get('table', {})
    if table.get('contentList'):
        return {str(x.get('questionTitle', chr(65+i))): '' for i,x in enumerate(table['contentList'])}
    return {}


def find_context(doc, index):
    doc = parse(doc)
    found = []
    def visit(n, ancestors):
        if not isinstance(n, dict):
            return
        if n.get('type') in {'serialNumberNode','DraggableInputNode'} and n.get('attrs',{}).get('index') == index:
            found.append(ancestors + [n])
        for x in n.get('content',[]):
            visit(x,ancestors+[n])
    if isinstance(doc,dict) and 'cellMatrix' in doc:
        for row in doc['cellMatrix']:
            if any(m.get('attrs',{}).get('index') == index for m in markers(row)):
                return clean(' | '.join(rich(c.get('content'),index) for c in row['cells']))
    visit(doc, [])
    if found:
        path=found[0]
        for parent in reversed(path[:-1]):
            if parent.get('type') in {'paragraph','listItem','tableRow'}:
                text=clean(rich(parent,index))
                if len(re.sub(r'\[.*?\]','',text).strip()) > 8:
                    return text
        # Some editors place the blank in a paragraph following its statement.
        top = doc.get('content', [])
        containing = next((i for i,n in enumerate(top) if any(m.get('attrs',{}).get('index') == index for m in markers(n))), None)
        if containing is not None and containing > 0:
            return clean(rich(top[containing-1]) + rich(top[containing],index))
    return clean(rich(doc,index))


def question_text(body, index, typ):
    if 'PARAGRAPH_MATCHING' in typ or 'CHARACTERISTIC_MATCHING' in typ:
        statements = body.get('table',{}).get('theadTitleList',[])
        if index < len(statements):
            return clean(rich(statements[index]))
    if 'PARAGRAPH_MARKS_MATCHING' in typ:
        # The title list may be in a different sequence when an example is supplied.
        doc = body.get('content')
        marks=markers(doc)
        if marks:
            text=find_context(doc,index)
            if len(text)<120:
                return text
        return f'为段落/部分 {chr(65+index)} 选择Heading（按该题组顺序）'
    if body.get('title'):
        return clean(rich(body['title']))
    doc=body.get('questionStem') or body.get('content')
    if doc:
        return find_context(doc,index)
    return clean(rich(body))


def type_label(typ, instructions, body, count):
    if re.search(r'choose.*heading|list of headings|correct heading',instructions,re.I):
        return 'Heading题'
    if 'OBJECTIVE_TF' in typ:
        return '判断题（YNNG）' if re.search(r'\bYES\b', instructions, re.I) else '判断题（TFNG）'
    if 'PARAGRAPH_MARKS_MATCHING' in typ:
        return 'Heading题'
    if 'PARAGRAPH_MATCHING' in typ:
        return '细节段落匹配'
    if 'CHOICE' in typ:
        return '多选题' if count>1 else '选择题'
    if 'CHARACTERISTIC_MATCHING' in typ:
        return '人名/观点匹配'
    if 'TEST_MATCHING' in typ:
        title=clean(rich(body.get('answerTitle')))
        if re.search(r'complete.*summary|summary using|summary below',instructions,re.I):
            return 'Summary选词填空'
        if re.search(r'researcher|people|person|scientist',instructions+' '+title,re.I):
            return '人名匹配'
        labels=list(options(body).values())
        name_pattern=r"^[A-Z][\w.'’–-]+(?:\s+(?:van|de|of|and|[A-Z][\w.'’–-]+)){1,6}$"
        if labels and all(re.match(name_pattern,x) for x in labels):
            return '人名匹配'
        return '短匹配（年份/选项等）'
    if 'PICTURE_GAP' in typ:
        return '图示填空'
    if 'TABLE_GAP' in typ:
        return '表格填空'
    if re.search(r'complete.*summary',instructions,re.I):
        return 'Summary填空'
    return '填空题'


def original_start(instructions, group_count):
    for pat in [r'boxes?\s+(\d+)\s*[-–—]\s*(\d+)',r'Questions?\s+(\d+)\s*[-–—]\s*(\d+)']:
        for match in re.finditer(pat,instructions,re.I):
            a,b=map(int,match.groups())
            if b-a+1==group_count:
                return a
    return None


def paragraphs(rootbody):
    doc=parse(rootbody.get('title') or rootbody.get('content') or rootbody.get('questionStem'))
    if not isinstance(doc,dict):
        return clean(rich(doc)),[]
    blocks=[line.strip() for n in doc.get('content',[]) if n.get('type')!='customSeparator' for line in clean(rich(n)).splitlines() if line.strip()]
    title=blocks[0] if blocks else ''
    rest=blocks[1:]
    label_candidates={m[1] for t in rest if (m:=re.match(r'^([A-L])(?:\s|$)',t))}
    labeled=len(label_candidates)>=3
    result=[]
    current=None
    for text in rest:
        label_match = re.match(r'^([A-L])(?:\s+|$)(.*)',text,re.S) if labeled else None
        if label_match:
            current=label_match[1]
            text=label_match[2].strip()
            if not text:
                continue
        label=current if labeled and current else ('导语' if labeled else f'P{len(result)+1}')
        if labeled and current and result and result[-1]['label']==current:
            result[-1]['text']+='\n'+text
        else:
            result.append({'label':label,'text':text})
    return title,result


def normalize(sources, checked_at, load_report):
    exercises=[]
    all_questions=[]
    articles={}
    checks=[]
    for source in sorted(sources,key=lambda s:s['test_id']):
        sections=load_report(source,'detail')['data']
        overview=load_report(source,'overview')['data'] or {}
        date=((overview.get('score') or {}).get('finishedAt') or '')[:10]
        selected=source.get('selected_passages')
        for section in sections:
            displayed=1
            for passage in section.get('stuAnswers',[]):
                groups=passage.get('childNodeList') or []
                done=passage.get('state')=='ANSWERED' and passage.get('reviewState')=='REVIEWED'
                if source.get('exam_reviewed'):
                    done=True
                if selected is not None and passage['questionId'] not in selected:
                    done=False
                rootbody=parse(passage.get('questionBody')) if done else {}
                title,paras=paragraphs(rootbody)
                article_key=hashlib.sha256(('\n'.join(p['text'] for p in paras)).encode()).hexdigest()[:12]
                if done:
                    articles.setdefault(article_key,{'id':article_key,'title':title,'paragraphs':paras,'image_urls':image_urls(rootbody)})
                exercise_id=f"{source['test_id']}-{passage['questionId']}"
                passage_dates=[x.get('correctAt','') for g in groups for x in (g.get('childNodeList') or [g]) if x.get('correctAt')]
                passage_date=max(passage_dates)[:10] if passage_dates else date
                exercise_rows=[]
                for group in groups:
                    leaves=group.get('childNodeList') or [group]
                    groupbody=parse(group.get('questionBody')) or {}
                    shared_body=next((parse(x.get('questionBody')) for x in leaves if isinstance(parse(x.get('questionBody')),dict) and parse(x.get('questionBody'))),{})
                    instructions=clean(rich(groupbody.get('title')))
                    group_count=sum(x.get('questionCount') or 1 for x in leaves)
                    orig_start=original_start(instructions,group_count)
                    offset=0
                    for index,leaf in enumerate(leaves):
                        count=leaf.get('questionCount') or 1
                        if not done:
                            displayed+=count
                            offset+=count
                            continue
                        body=parse(leaf.get('questionBody')) or shared_body
                        answers=flatten_answer(leaf.get('answer'))
                        correct=flatten_answer(leaf.get('referenceAnswer'))
                        opts=options(body)
                        typ=leaf.get('type','')
                        if not answers:
                            status='未作答'
                        elif leaf.get('correctResult')=='CORRECT':
                            status='正确'
                        elif leaf.get('correctResult')=='PARTIALLY_CORRECT' or 0<float(leaf.get('score') or 0)<float(leaf.get('totalScore') or count):
                            status='部分正确'
                        else:
                            status='答错'
                        def answer_text(values):
                            if not values:
                                return '未作答'
                            if 'OBJECTIVE_TF' in typ:
                                return ' / '.join(opts.get(x,x) for x in values)
                            if opts:
                                return '；'.join(f'{x} {opts[x]}' if x in opts and opts[x] else x for x in values)
                            def show_space(value):
                                if value != value.strip():
                                    visible=value.replace(' ','␠').replace('\t','⇥').replace('\n','↵')
                                    return visible+'（有首尾空白）'
                                return value
                            return ' / '.join(show_space(x) for x in dict.fromkeys(values))
                        number=str(displayed) if count==1 else f'{displayed}-{displayed+count-1}'
                        original=(str(orig_start+offset) if count==1 else f'{orig_start+offset}-{orig_start+offset+count-1}') if orig_start is not None else ''
                        if not original:
                            source_mark=next((m for m in markers(body) if m.get('attrs',{}).get('index')==index),None)
                            source_label=(source_mark or {}).get('attrs',{}).get('text') or (source_mark or {}).get('attrs',{}).get('label')
                            if source_label and str(source_label).isdigit():
                                original=str(source_label)
                        text=question_text(body,index,typ)
                        doc=body.get('questionStem') or body.get('content') or body.get('table')
                        full_context=clean(rich(doc)) if doc else ''
                        row={
                            'id':f"{source['test_id']}-{leaf['questionId']}", 'exercise_id':exercise_id,
                            'source_type':source['source_type'],'source_name':source['name'],
                            'assignment_group':section.get('sectionName',''),'passage_code':passage.get('questionName',''),
                            'article_id':article_key,'passage_title':title,'date':passage_date,
                            'question_id':leaf['questionId'],'group_id':group['questionId'],
                            'question_number':number,'original_number':original,
                            'question_type':type_label(typ,instructions,body,count),'raw_type':typ,
                            'instructions':instructions,'question':text,'full_context':full_context,
                            'options':opts,'student_answer_raw':answers,'correct_answer_raw':correct,
                            'student_answer':answer_text(answers),'correct_answer':answer_text(correct),
                            'status':status,'points':count,'score':float(leaf.get('score') or 0),
                            'image_urls':image_urls(body),
                        }
                        exercise_rows.append(row)
                        all_questions.append(row)
                        displayed+=count
                        offset+=count
                if done:
                    exercise={
                        'id':exercise_id,'source_type':source['source_type'],'source_name':source['name'],
                        'assignment_group':section.get('sectionName',''),'passage_code':passage.get('questionName',''),
                        'title':title,'article_id':article_key,'date':passage_date,
                        'website_score':float(passage.get('score') or 0),'website_total':float(passage.get('totalScore') or 0),
                        'question_groups':len(exercise_rows),'points':sum(x['points'] for x in exercise_rows),
                        'score':sum(x['score'] for x in exercise_rows),
                        'wrong_rows':sum(x['status'] in {'答错','部分正确'} for x in exercise_rows),
                        'unanswered_rows':sum(x['status']=='未作答' for x in exercise_rows),
                    }
                    exercises.append(exercise)
                    checks.append({'exercise_id':exercise_id,'points_match':exercise['points']==exercise['website_total'],'score_match':abs(exercise['score']-exercise['website_score'])<0.00001})
    payload={'checked_at':checked_at,'exercises':exercises,'articles':list(articles.values()),'questions':all_questions}
    return payload, checks
