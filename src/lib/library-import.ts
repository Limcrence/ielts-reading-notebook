import type { Annotation, Article, Exercise, Library, Question } from './types.ts';

export const LIBRARY_FILE_LIMIT = 15_000_000;
const statuses = new Set(['正确', '答错', '部分正确', '未作答']);

function object(value: unknown, at: string): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error(at + '必须是对象。');
  }
  return value as Record<string, unknown>;
}

function list(value: unknown, at: string, maximum: number): unknown[] {
  if (!Array.isArray(value) || value.length > maximum) {
    throw new Error(at + '必须是有效列表。');
  }
  return value;
}

function string(value: unknown, at: string, maximum = 1000): string {
  if (typeof value !== 'string' || value.length > maximum) throw new Error(at + '格式不正确。');
  return value;
}

function key(value: unknown, at: string): string {
  const id = string(value, at, 100);
  if (!/^[a-zA-Z0-9][a-zA-Z0-9_.:-]*$/.test(id)) throw new Error(at + '需要稳定的英文或数字编号。');
  return id;
}

function numeric(value: unknown, at: string): number {
  if (typeof value !== 'number' || !Number.isFinite(value) || value < 0) {
    throw new Error(at + '必须是非负数字。');
  }
  return value;
}

function integer(value: unknown, at: string): number {
  const count = numeric(value, at);
  if (!Number.isSafeInteger(count)) throw new Error(at + '必须是整数。');
  return count;
}

function answers(value: unknown, at: string): string[] {
  return list(value, at, 10).map(answer => string(answer, at, 256));
}

function index<T extends {id: string}>(rows: T[], at: string): Map<string, T> {
  const map = new Map(rows.map(row => [row.id, row]));
  if (!rows.length || map.size !== rows.length) throw new Error(at + '为空或含有重复 ID。');
  return map;
}

function annotation(
  value: unknown, article: Article, at: string, aliases?: Map<string, string[]>,
): Annotation | undefined {
  if (value === undefined) return;
  const row = object(value, at + '解析');
  const evidence = list(row.evidence, at + '原文依据', 12).map(item => {
    const entry = object(item, at + '原文依据');
    const paragraph = string(entry.paragraph, at + '段号', 30);
    const quote = string(entry.text, at + '证据句', 5000);
    const labels = aliases?.get(paragraph) ?? [paragraph];
    const matches = article.paragraphs.filter(p => labels.includes(p.label) && p.text.includes(quote));
    if (!quote.trim() || matches.length !== 1) {
      throw new Error(at + '的证据句在指定段落里找不到。');
    }
    return {paragraph:matches[0].label, text:quote};
  });
  const explanation = string(row.explanation, at + '解析', 5000);
  if (!evidence.length || !explanation.trim()) throw new Error(at + '的解析缺少原文依据或解释。');
  return {
    evidence, explanation, anchors:evidence.map(item => item.text),
    paraphrases:string(row.paraphrases ?? '', at + '同义替换', 3000),
    location:[...new Set(evidence.map(item => item.paragraph))].join('、'),
  };
}

function metadata(row: Record<string, unknown>, at: string) {
  return {
    source_type:string(row.source_type, at + '来源', 30),
    source_name:string(row.source_name, at + '考试名称', 160),
    assignment_group:string(row.assignment_group ?? '', at + '练习组', 160),
    passage_code:string(row.passage_code ?? '', at + '篇章编号', 80),
    date:string(row.date ?? '', at + '日期', 10),
  };
}

export function validateLibrary(value: unknown, stored = false): Library {
  const input = object(value, '题库');
  // Imports are capped per file. A student's saved library can span several validated files.
  const rowLimit = stored ? Number.MAX_SAFE_INTEGER : 2000;
  const labelAliases = new Map<string, Map<string, string[]>>();
  const articles = list(input.articles, '文章', rowLimit).map((value, i): Article => {
    const at = '文章 ' + (i + 1) + ' ';
    const row = object(value, at);
    const paragraphs = list(row.paragraphs, at + '段落', 250).map(value => {
      const paragraph = object(value, at + '段落');
      return {label:string(paragraph.label, at + '段号', 30), text:string(paragraph.text, at + '段落原文', 30000)};
    });
    const title = string(row.title, at + '标题', 300);
    if (!title.trim() || !paragraphs.length || paragraphs.some(p => !p.label.trim() || !p.text.trim())) {
      throw new Error(at + '标题或段落缺失。');
    }
    const id = key(row.id, at + 'ID');
    const reserved = new Set(paragraphs.map(p => p.label));
    const aliases = new Map<string, string[]>();
    const normalized = paragraphs.map(p => {
      const raw = p.label;
      const variants = aliases.get(raw) ?? [];
      let label = raw;
      if (variants.length) {
        let next = variants.length + 1;
        do { label = raw.slice(0, 24) + '-' + next++; } while (reserved.has(label));
        reserved.add(label);
      }
      variants.push(label);
      aliases.set(raw, variants);
      return {...p, label};
    });
    labelAliases.set(id, aliases);
    return {id, title, paragraphs:normalized};
  });
  const byArticle = index(articles, '文章列表');
  const exercises = list(input.exercises, '练习', rowLimit).map((value, i): Exercise => {
    const at = '练习 ' + (i + 1) + ' ';
    const row = object(value, at);
    const articleId = key(row.article_id, at + 'Article ID');
    const article = byArticle.get(articleId);
    if (!article) throw new Error(at + '关联的文章不存在。');
    return {
      ...metadata(row, at), id:key(row.id, at + 'ID'), article_id:articleId, title:article.title,
      website_score:0, website_total:0, wrong_rows:0, unanswered_rows:0,
    };
  });
  const byExercise = index(exercises, '练习列表');
  const positions = new Set<string>();
  const questions = list(input.questions, '题目', rowLimit).map((value, i): Question => {
    const row = object(value, '题目');
    const at = '题目 ' + (i + 1) + ' ';
    const exerciseId = key(row.exercise_id, at + 'Exercise ID');
    const exercise = byExercise.get(exerciseId);
    const article = exercise && byArticle.get(exercise.article_id);
    if (!exercise || !article || row.article_id !== article.id) throw new Error(at + '关联的练习或文章不正确。');
    const number = string(row.question_number, at + '报告题号', 25);
    const slot = exerciseId + ':' + number;
    if (!number.trim() || positions.has(slot)) throw new Error(at + '在同一篇练习里题号为空或重复。');
    positions.add(slot);
    const status = string(row.status, at + '作答状态', 5);
    const points = integer(row.points, at + '满分');
    const score = numeric(row.score, at + '得分');
    if (!statuses.has(status) || points < 1 || points > 10 || score > points) {
      throw new Error(at + '作答状态或原始得分不正确。');
    }
    const options = Object.fromEntries(Object.entries(object(row.options, at + '选项')).map(([id, label]) =>
      [key(id, at + '选项编号'), string(label, at + '选项内容', 4000)]));
    const answer = answers(row.correct_answer_raw, at + '正确答案');
    if (!answer.length || answer.some(entry => !entry.trim() ||
        (Object.keys(options).length > 0 && !Object.hasOwn(options, entry)))) {
      throw new Error(at + '缺少正确答案，或答案编号不在选项中。');
    }
    const student = answers(row.student_answer_raw, at + '原答案');
    const prompt = string(row.question, at + '题干', 12000);
    if (!prompt.trim()) throw new Error(at + '缺少题干。');
    const review = annotation(row.review, article, at, labelAliases.get(article.id));
    const localImages = list(row.image_urls ?? [], at + '图示', 12)
      .map(item => string(item, at + '图示', 8_000_000))
      .filter(url => /^data:image\/(?:png|jpeg|webp);base64,[A-Za-z0-9+/]+={0,2}$/.test(url));
    exercise.website_score += score;
    exercise.website_total += points;
    exercise.wrong_rows += Number(status === '答错' || status === '部分正确');
    exercise.unanswered_rows += Number(status === '未作答');
    return {
      ...metadata(exercise, at), id:key(row.id, at + 'ID'),
      article_id:article.id, exercise_id:exerciseId, passage_title:article.title,
      question_number:number, original_number:string(row.original_number ?? '', at + '原卷题号', 25),
      question_type:string(row.question_type, at + '题型', 70),
      raw_type:string(row.raw_type ?? '', at + '原始题型', 70),
      group_id:integer(row.group_id, at + '题组编号'), question:prompt,
      instructions:string(row.instructions ?? '', at + '题组指示', 10000),
      full_context:string(row.full_context ?? '', at + '题组上下文', 30000),
      options, status, points, score, student_answer_raw:student, correct_answer_raw:answer,
      student_answer:student.map(choice => options[choice] ?? choice).join(' / '),
      correct_answer:answer.map(choice => options[choice] ?? choice).join(' / '),
      report_url:'', image_urls:localImages, ...(review ? {review} : {}),
    };
  });
  index(questions, '题目列表');
  if (exercises.some(exercise => exercise.website_total === 0)) {
    throw new Error('有的练习没有关联题目。');
  }
  return {checked_at:string(input.checked_at ?? '', '整理日期', 10), articles, exercises, questions};
}

function upsert<T extends {id: string}>(
  a: T[], b: T[], identity: (row: T) => unknown, join = (_old: T, incoming: T) => incoming,
): T[] {
  const rows = new Map(a.map(row => [row.id, row]));
  for (const item of b) {
    const existing = rows.get(item.id);
    if (existing && JSON.stringify(identity(existing)) !== JSON.stringify(identity(item))) {
      throw new Error('编号 ' + item.id + ' 与已有不同版本的内容冲突，需为另一版本使用新编号。');
    }
    rows.set(item.id, existing ? join(existing, item) : item);
  }
  return [...rows.values()];
}

export function mergeLibraries(current: Library | null, incoming: Library): Library {
  if (!current) return incoming;
  return validateLibrary({
    checked_at:incoming.checked_at || current.checked_at,
    articles:upsert(current.articles, incoming.articles, item => [item.title, item.paragraphs]),
    exercises:upsert(current.exercises, incoming.exercises, item => item.article_id),
    questions:upsert(current.questions, incoming.questions, item => [
      item.exercise_id, item.question_number, item.group_id, item.question, item.question_type,
      item.full_context, item.instructions, Object.entries(item.options).sort(), item.points,
      [...item.correct_answer_raw].sort(),
    ], (existing, item) => ({
      ...item, review:item.review ?? existing.review,
      image_urls:item.image_urls.length ? item.image_urls : existing.image_urls,
    })),
  }, true);
}
