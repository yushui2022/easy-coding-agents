import React,{useEffect,useRef,useState} from 'react';
import {GithubLogo, ArrowClockwise, LockSimple, Check, Copy, Terminal} from '@phosphor-icons/react';

const invoke = (method:string, params:Record<string,unknown>={}) => window.eca.invoke(method, params);
const clock = (seconds:number) => `${Math.floor(seconds/60)}:${String(Math.max(0,seconds%60)).padStart(2,'0')}`;

type Repo = {full_name:string; private:boolean; description:string; updated_at:string};
type Device = {userCode:string; verificationUri:string; interval:number; expiresAt:number};

// The token only travels from this pane to the main process, which stores it
// encrypted. Nothing here ever reads it back; we only show the login name.
//
// Signing in opens GitHub's device page and polls for the token, so the account
// password never passes through this app. Pasting a token and reusing a local
// `gh` login remain one section below for people who already have one.
export function GitHubPane({onOpened, blocked}:{onOpened:()=>void; blocked?:boolean}) {
  const [status,setStatus]=useState<any>(null);
  const [token,setToken]=useState('');
  const [repos,setRepos]=useState<Repo[]>([]);
  const [busy,setBusy]=useState(false);
  const [note,setNote]=useState('');
  const [device,setDevice]=useState<Device|null>(null);
  const [left,setLeft]=useState(0);
  const [copied,setCopied]=useState(false);
  const [clientDraft,setClientDraft]=useState('');
  const interval=useRef(5);

  useEffect(()=>{void invoke('github.status').then(setStatus).catch(()=>{});},[]);
  useEffect(()=>{
    if(!device)return;
    const timer=setInterval(()=>setLeft(Math.max(0,Math.round((device.expiresAt-Date.now())/1000))),1000);
    return()=>clearInterval(timer);
  },[device]);
  // GitHub rate-limits the poll endpoint, so the loop only ever waits the interval
  // GitHub itself handed out and backs off when it answers slow_down.
  useEffect(()=>{
    if(!device)return;
    let stopped=false;
    let timer:any;
    const tick=async()=>{
      try {
        const next=await invoke('github.oauth.poll',{});
        if(stopped)return;
        if(next.status==='connected'){
          setDevice(null);
          setNote('已用 GitHub 登录：'+(next.login||''));
          setStatus(await invoke('github.status'));
          await loadRepos();
          return;
        }
        if(next.status==='pending'){timer=setTimeout(tick,interval.current*1000);return;}
        if(next.status==='slow_down'){interval.current=Math.max(10,Number(next.interval)||10);timer=setTimeout(tick,interval.current*1000);return;}
        setDevice(null);
        setNote(next.message||'登录没有完成，请重新开始。');
      } catch(error) {
        if(!stopped){setDevice(null);setNote(String(error));}
      }
    };
    timer=setTimeout(tick,interval.current*1000);
    return()=>{stopped=true;clearTimeout(timer);};
  },[device?.userCode]);
  useEffect(()=>{if(!copied)return;const timer=setTimeout(()=>setCopied(false),1800);return()=>clearTimeout(timer);},[copied]);

  const loadRepos = async () => {
    setBusy(true);setNote('');
    try {setRepos(await invoke('github.repos'));}
    catch (error) {setNote(String(error));}
    finally {setBusy(false);}
  };
  const refresh = async () => {setStatus(await invoke('github.status').catch(()=>null));};
  const startLogin = async () => {
    if(busy)return;
    setBusy(true);setNote('');
    try {
      const start=await invoke('github.oauth.start');
      interval.current=Number(start.interval)||5;
      setLeft(Number(start.expiresIn)||900);
      setDevice({userCode:String(start.userCode||''),verificationUri:String(start.verificationUri||''),
        interval:interval.current,expiresAt:Date.now()+(Number(start.expiresIn)||900)*1000});
    } catch (error) {setNote(String(error));}
    finally {setBusy(false);}
  };
  const cancelLogin = async () => {
    setDevice(null);
    try {await invoke('github.oauth.cancel');} catch { /* a cancelled login has nothing to report */ }
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
  const loginFromGh = async () => {
    if(busy)return;
    setBusy(true);setNote('');
    try {
      setStatus(await invoke('github.gh.login'));
      await loadRepos();
    } catch (error) {setNote(String(error));}
    finally {setBusy(false);}
  };
  const saveClient = async () => {
    if(busy||!clientDraft.trim())return;
    setBusy(true);setNote('');
    try {
      await invoke('github.oauth.client',{clientId:clientDraft.trim()});
      setClientDraft('');
      await refresh();
      setNote('Client ID 已保存，现在可以直接用 GitHub 登录了。');
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
  const copyCode = async () => {
    if(!device)return;
    if(await window.eca.copy(device.userCode).catch(()=>false)) setCopied(true);
  };

  return <section className="connection-editor personal-pane" aria-label="GitHub">
    <div className="connection-scroll">
      <header className="connection-heading"><div><h3>GitHub</h3><p>用 GitHub 账号登录后，这里直接列出你的仓库，点一下就克隆成本地项目。</p></div>
        {status?.connected&&<span className="connection-default-badge"><Check size={12}/>{status.login}</span>}</header>

      {!status?.connected&&<section className="connection-section" aria-labelledby="github-login-heading">
        <h4 id="github-login-heading"><GithubLogo size={15}/>登录</h4>

        {status?.oauthReady
          ? (device
            ? <div className="github-device">
                <p>在浏览器打开的页面里输入这个码：</p>
                <div className="github-device-row">
                  <button type="button" className="github-code" title="点击复制" onClick={()=>void copyCode()}>{device.userCode}</button>
                  <button type="button" onClick={()=>void copyCode()}>{copied?<><Check size={14}/>已复制</>:<><Copy size={14}/>复制</>}</button>
                </div>
                <p>还没打开页面？<button type="button" className="text-link" onClick={()=>{void invoke('link.open',{url:device.verificationUri}).catch(()=>{});}}>在浏览器中打开 {device.verificationUri.replace(/^https?:\/\//,'')}</button></p>
                <div className="github-device-row">
                  <span className="github-waiting" role="status">{left>0?`等待你在 GitHub 上确认…还剩 ${clock(left)}`:'验证码即将过期'}</span>
                  <button type="button" disabled={busy} onClick={()=>void cancelLogin()}>取消</button>
                </div>
              </div>
            : <div className="actions config-actions"><button className="primary" disabled={busy||blocked} onClick={()=>void startLogin()}><GithubLogo size={15}/>{busy?'正在联系 GitHub…':'用 GitHub 登录'}</button></div>)
          : <div className="github-setup">
              <p className="fine-print">还没有配置 OAuth App 的 Client ID，所以「用 GitHub 登录」暂时不可用——下面两种方式现在就能用。</p>
              <details className="github-client">
                <summary>配置 OAuth App Client ID（一次性，之后所有人直接点登录）</summary>
                <p className="fine-print">在 GitHub → Settings → Developer settings → OAuth Apps 新建一个应用，勾选 <code>Enable Device Flow</code>，把它的 Client ID 填进来。Client ID 不是密钥，可以随产品分发。</p>
                <div className="field"><label htmlFor="github-client-id">Client ID</label>
                  <input id="github-client-id" type="text" autoComplete="off" spellCheck={false} value={clientDraft} placeholder="Iv1.0123456789abcdef" disabled={busy}
                    onChange={event=>setClientDraft(event.target.value)}
                    onKeyDown={event=>{if(event.key==='Enter'&&!event.nativeEvent.isComposing)void saveClient();}}/></div>
                <div className="actions config-actions"><button disabled={busy||!clientDraft.trim()} onClick={()=>void saveClient()}>保存 Client ID</button></div>
              </details>
            </div>}

        {status?.ghAvailable&&!device&&<div className="actions config-actions">
          <button disabled={busy||blocked} onClick={()=>void loginFromGh()}><Terminal size={14}/>使用本机 gh 登录</button>
        </div>}

        {!device&&<details className="github-client github-token">
          <summary>{status?.oauthReady||status?.ghAvailable?'或者用访问令牌连接':'用访问令牌连接'}</summary>
          <div className="field"><label htmlFor="github-token">访问令牌</label>
            <input id="github-token" type="password" autoComplete="off" spellCheck={false}
              placeholder="ghp_… 或 github_pat_…" value={token} disabled={busy||blocked}
              onChange={event=>setToken(event.target.value)}
              onKeyDown={event=>{if(event.key==='Enter'&&!event.nativeEvent.isComposing)void connect();}}/></div>
          <div className="actions config-actions"><button disabled={busy||blocked||!token.trim()} onClick={()=>void connect()}>连接账号</button></div>
          <p className="fine-print">在 GitHub → Settings → Developer settings → Personal access tokens 创建，勾选 <code>repo</code> 即可读私有仓库。</p>
        </details>}

        <p className="fine-print">只申请读取仓库和克隆需要的 <code>repo</code> 权限；令牌用系统加密保存在本机，界面只显示账号名，随时可以在 GitHub 的 Applications 里撤销。</p>
        {status&&!status.encryptionAvailable&&<p className="fine-print">系统加密不可用，因此不会保存令牌。</p>}
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
