import {readFile} from 'node:fs/promises';
import {validateLibrary, LIBRARY_FILE_LIMIT} from '../src/lib/library-import.ts';

try {
  const filename = process.argv[2] || new URL('../examples/reading-library.json', import.meta.url);
  const data = await readFile(filename);
  if (data.length > LIBRARY_FILE_LIMIT) throw new Error('题库文件超过 15 MB。');
  const library = validateLibrary(JSON.parse(data.toString('utf8')));
  const counts = {correct: 0, wrong: 0, partial: 0, unanswered: 0, reviewed: 0};
  const key = {'正确':'correct','答错':'wrong','部分正确':'partial','未作答':'unanswered'};
  for (const q of library.questions) {
    counts[key[q.status]]++;
    if (q.review) counts.reviewed++;
  }
  console.log(JSON.stringify({exercises:library.exercises.length, questions:library.questions.length, ...counts}));
} catch (error) {
  console.error(error instanceof SyntaxError ? '文件不是有效的 JSON。' : error.message);
  process.exitCode = 1;
}
