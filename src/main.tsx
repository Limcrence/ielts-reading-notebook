import {useEffect, useRef, useState} from 'react';
import {createRoot} from 'react-dom/client';
import {BookOpen} from 'lucide-react';
import ReviewApp, {initializeLibrary} from './review-app';
import {LIBRARY_FILE_LIMIT, validateLibrary} from './lib/library-import';
import {addPersonalLibrary, readPersonalLibrary} from './lib/library-storage';
import type {Library} from './lib/types';
import demo from '../examples/reading-library.json';
import './reading.css';
import './daily.css';
import './template.css';

function App() {
  const [scope, setScope] = useState<'demo' | 'personal' | null>(null);
  const [personal, setPersonal] = useState<Library | null>(null);
  const [checking, setChecking] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    let active = true;
    readPersonalLibrary().then(library => {
      if (active) setPersonal(library);
    }).catch(() => {
      if (active) setError('暂时无法读取本机题库。请确认浏览器允许本站保存数据。');
    }).finally(() => {
      if (active) setChecking(false);
    });
    return () => { active = false; };
  }, []);

  function open(library: Library, nextScope: 'demo' | 'personal') {
    initializeLibrary(library);
    setScope(nextScope);
  }

  async function importFile(file: File) {
    if (file.size > LIBRARY_FILE_LIMIT) {
      setError('文件超过 15 MB，请分批导入，每批保留完整文章和题组。');
      return;
    }
    setError('');
    setBusy(true);
    try {
      const result = await addPersonalLibrary(validateLibrary(JSON.parse(await file.text())));
      setPersonal(result);
      open(result, 'personal');
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '导入失败，已有题库未被替换。');
    } finally {
      setBusy(false);
    }
  }

  if (scope) return <ReviewApp key={scope} scope={scope} onLibrary={() => setScope(null)}/>;

  return <main className="unlock-page">
    <section className="unlock-card">
      <span className="unlock-icon"><BookOpen size={26}/></span>
      <h1>雅思阅读错题本</h1>
      <p>{checking ? '正在查看本机题库…' : personal ? `个人题库 · ${personal.questions.length} 个题组` : '导入个人题库，从自己做错的题开始复习。'}</p>
      <div className="template-actions">
        {personal && <button className="button primary" disabled={busy} onClick={() => open(personal, 'personal')}>继续我的复习</button>}
        <button className={'button ' + (!personal ? 'primary' : '')} disabled={checking || busy}
          onClick={() => inputRef.current?.click()}>{busy ? '正在导入…' : '导入我的题库'}</button>
        <button className="button" disabled={busy} onClick={() => open(validateLibrary(demo), 'demo')}>试用示例题库</button>
      </div>
      <input ref={inputRef} className="visually-hidden" type="file" accept=".json,application/json"
        onChange={event => {
          const file = event.currentTarget.files?.[0];
          event.currentTarget.value = '';
          if (file) void importFile(file);
        }}/>
      {error && <p className="unlock-error" role="alert">{error}</p>}
    </section>
  </main>;
}

createRoot(document.getElementById('root')!).render(<App/>);
