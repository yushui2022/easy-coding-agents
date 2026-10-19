import React from 'react';
import {Code, Bug, TestTube} from '@phosphor-icons/react';

export function Welcome({project,choosing,onProject,onDraft}:{project:string;choosing:boolean;onProject:()=>void;onDraft:(value:string)=>void}) {
  return <section className="welcome" aria-label="新任务">
    <img className="welcome-art" src="./welcome-loop.png" width={64} height={64} alt="" aria-hidden="true" decoding="async"/>
    <h1>{project?<><span>今天想在 </span><button className="welcome-project" title={project} disabled={choosing} onClick={onProject} aria-label="切换工作项目">{project}</button><span> 做点什么？</span></>:<>今天，从哪里开始？</>}</h1>
    {!project&&<p>选择一个项目，把想法变成代码。</p>}
    <div className="suggestions" aria-label="任务示例">
      {[[Code,'了解项目','梳理项目结构、运行方式和核心模块，先不要修改代码。'],[Bug,'排查问题','帮我定位并修复一个问题：'],[TestTube,'补充测试','检查项目现有测试，为缺少覆盖的关键逻辑补充测试。']].map(([Icon,text,value])=>{
        const SuggestionIcon=Icon as typeof Code;
        return <button key={String(text)} onClick={()=>onDraft(String(value))}><SuggestionIcon size={15}/>{String(text)}</button>;
      })}
    </div>
  </section>;
}
