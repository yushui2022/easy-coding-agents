import React,{useEffect,useState} from 'react';
import {GithubLogo, ArrowClockwise, LockSimple, Check} from '@phosphor-icons/react';

const invoke = (method:string, params:Record<string,unknown>={}) => window.eca.invoke(method, params);

type Repo = {full_name:string; private:boolean; description:string; updated_at:string};

// The token only travels from this input to the main process, which stores it
// encrypted. Nothing here ever reads it back; we only show the login name.
export function GitHubPane({onOpened, blocked}:{onOpened:()=>void; blocked?:boolean}) {
  const [status,setStatus]=useState<any>(null);
  const [token,setToken]=useState('');
  const [repos,setRepos]=useState<Repo[]>([]);
  const [busy,setBusy]=useState(false);
  const [note,setNote]=useState('');

  useEffect(()=>{void invoke('github.status').then(setStatus).catch(()=>{});},[]);
  const loadRepos = async () => {
    setBusy(true);setNote('');
    try {setRepos(await invoke('github.repos'));}
    catch (error) {setNote(String(error));}
    finally {setBusy(false);}
  };
  const connect = async () => {
    if(!token.trim()||busy)return;
    setBusy(true);setNote('');
    try {
      const next = await invoke('github.connect',{token});
      setStatus(next);setToken('');
      await loadRepos();
    } catch (error) {setNote(String(error));}
    finally {setBusy(false);}
  };
  const disconnect = async () => {
    setBusy(true);setNote('');
    try {setStatus(await invoke('github.disconnect'));setRepos([]);}
    catch (error) {setNote(String(error));}
    finally {setBusy(false);}
  };
  const clone = async (repo:Repo) => {
    setBusy(true);setNote('正在克隆 '+repo.full_name+' …');
    try {
      await invoke('github.clone',{repo:repo.full_name});
      setNote('已克隆并打开 '+repo.full_name);
      onOpened();
    } catch (error) {setNote(String(error));}
    finally {setBusy(false);}
  };

  return <section className="connection-editor personal-pane" aria-label="GitHub">
    <div className="connection-scroll">
      <header className="connection-heading"><div><h3>GitHub</h3><p>登录后可以直接把仓库克隆下来，作为本地项目打开。</p></div>
        {status?.connected&&<span className="connection-default-badge"><Check size={12}/>{status.login}</span>}</header>

      {!status?.connected&&<section className="connection-section" aria-labelledby="github-token-heading">
        <h4 id="github-token-heading"><GithubLogo size={15}/>登录</h4>
        <div className="field"><label htmlFor="github-token">访问令牌</label>
          <input id="github-token" type="password" autoComplete="off" spellCheck={false}
            placeholder="ghp_… 或 github_pat_…" value={token} disabled={busy||blocked}
            onChange={event=>setToken(event.target.value)}
            onKeyDown={event=>{if(event.key==='Enter'&&!event.nativeEvent.isComposing)void connect();}}/></div>
        <div className="actions config-actions"><button className="primary" disabled={busy||blocked||!token.trim()} onClick={()=>void connect()}>连接账号</button></div>
        <p className="fine-print">在 GitHub → Settings → Developer settings → Personal access tokens 创建，勾选 <code>repo</code> 即可读私有仓库。令牌用系统加密保存在本机，界面只显示账号名。</p>
        {status&&!status.encryptionAvailable&&<p className="fine-print">系统加密不可用，因此不会保存令牌；可以每次手动输入。</p>}
      </section>}

      {status?.connected&&<>
        <section className="connection-section" aria-labelledby="github-account-heading">
          <h4 id="github-account-heading"><LockSimple size={15}/>账号</h4>
          <div className="profile-identity">
            <span className="profile-avatar" aria-hidden="true">{String(status.login||'?').slice(0,1).toUpperCase()}</span>
            <div><strong>{status.login}</strong><small>{status.encrypted?'令牌已加密保存':'令牌仅在本次会话有效'}</small></div>
          </div>
          <div className="actions config-actions">
            <button disabled={busy||blocked} onClick={()=>void loadRepos()}><ArrowClockwise size={14}/>{busy?'正在读取…':'刷新仓库'}</button>
            <button disabled={busy} onClick={()=>void disconnect()}>断开连接</button>
          </div>
        </section>
        <section className="connection-section" aria-labelledby="github-repos-heading">
          <h4 id="github-repos-heading"><GithubLogo size={15}/>仓库{repos.length?`（${repos.length}）`:''}</h4>
          {!repos.length&&<p className="fine-print">{busy?'正在读取仓库列表…':'还没有加载仓库，点上面的「刷新仓库」。'}</p>}
          <ul className="repo-list">{repos.map(repo=><li key={repo.full_name} className="repo-row">
            <div className="repo-copy"><strong>{repo.full_name}</strong>
              <small>{repo.private?'私有':'公开'}{repo.description?' · '+repo.description:''}</small></div>
            <button disabled={busy||blocked} onClick={()=>void clone(repo)}>克隆并打开</button>
          </li>)}</ul>
        </section>
      </>}

      {note&&<p className="config-status" role="status">{note}</p>}
    </div>
  </section>;
}
