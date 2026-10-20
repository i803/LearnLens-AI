'use client'

import React, { useEffect, useMemo, useRef, useState } from 'react'
import Link from 'next/link'
import { usePathname, useRouter } from 'next/navigation'
import { ArrowRight, BarChart3, BookOpen, BrainCircuit, Check, ChevronRight, CircleHelp, FileCheck2, FileText, Flame, Gauge, Menu, MoreHorizontal, Plus, RefreshCw, Search, Sparkles, Target, Upload, Users, X, AlertTriangle, Clock3, Pencil, RotateCcw, Send, Database, Activity } from 'lucide-react'
import { api, slugify } from '@/lib/api'
import { getStudentId, loadState, saveState, type SessionState } from '@/lib/session'

import { ProgressData, TeacherData, HealthData, normalizeProgressData, conceptLabel, Logo, Button, ProgressBar, StatCard, Shell, PageHeader, Thinking } from '@/components/ui-kit'

export function TestPage(){
  const router=useRouter();
  const [subject,setSubject]=useState('Mathematics');
  const [topic,setTopic]=useState('Quadratic Equations');
  const [items,setItems]=useState<any[]>([]);
  const [index,setIndex]=useState(0);
  const [answer,setAnswer]=useState('');
  const [results,setResults]=useState<{correct:boolean}[]>([]);
  const [answers,setAnswers]=useState<Record<string,string>>({});
  const [loading,setLoading]=useState(false);
  const [error,setError]=useState('');
  async function start(){
    localStorage.setItem('learnlens_bundled_demo','0');
    if(!subject.trim()||!topic.trim()) return;
    setLoading(true); setError(''); setItems([]); setResults([]); setAnswers({}); setIndex(0); setAnswer('');
    try{
      const conceptId=slugify(`${subject}-${topic}`);
      const d=await api<any>('/diagnostic/generate',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({studentId:getStudentId(),conceptId,conceptName:topic.trim(),subject:subject.trim(),topic:topic.trim(),count:5,mode:'topic',sourceQuestions:[],sourceTopics:[]})});
      if(!Array.isArray(d?.questions)||d.questions.length<3) throw new Error('The diagnostic did not return enough questions.');
      saveState('learnlens_session',{subject:subject.trim(),topic:topic.trim(),conceptId,conceptName:topic.trim(),quickTest:{questions:d.questions,answers:{}}});
      setItems(d.questions);
    }catch(e){setError(e instanceof Error?e.message:'Could not build the quick test.')}finally{setLoading(false)}
  }
  async function choose(value:string){
    if(!items[index]) return;
    const current=items[index];
    const correct=String(value).trim().toLowerCase()===String(current.correctAnswer||'').trim().toLowerCase();
    const updatedAnswers={...answers,[current.questionId]:value};
    const next=[...results,{correct}];
    setAnswers(updatedAnswers); setResults(next); setAnswer('');
    if(index===items.length-1){
      const score=Math.round(next.filter(x=>x.correct).length/items.length*100);
      const session=loadState<any>('learnlens_session',{});
      saveState('learnlens_session',{...session,subject,topic,quickTestResult:{score,correct:next.filter(x=>x.correct).length,total:items.length,answers:updatedAnswers}});
      try{
        await api('/diagnostic/evaluate',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({studentId:getStudentId(),conceptId:session.conceptId||slugify(`${subject}-${topic}`),answers:updatedAnswers})});
      }catch{ /* quick-test result remains usable even when persistence is unavailable */ }
      return;
    }
    setIndex(v=>v+1);
  }
  if(!items.length) return <Shell><div className="mx-auto max-w-3xl px-1"><PageHeader eyebrow="Quick understanding check" title="Test what you know." description="Choose any subject and topic. LearnLens creates a short five-question check and shows what to learn next."/><div className="rounded-2xl border border-[#dbe4dc] bg-white p-6 sm:p-8"><label className="text-sm font-semibold text-[#183e3c]" htmlFor="quick-subject">Subject</label><input id="quick-subject" value={subject} onChange={e=>setSubject(e.target.value)} className="mt-2 w-full rounded-xl border border-[#cbd9cf] bg-[#fbfcfa] px-4 py-3 text-base outline-none focus:border-[#6d9e8e] focus:ring-4 focus:ring-[#dcebe5]"/><label className="mt-6 block text-sm font-semibold text-[#183e3c]" htmlFor="quick-topic">Topic</label><input id="quick-topic" value={topic} onChange={e=>setTopic(e.target.value)} className="mt-2 w-full rounded-xl border border-[#cbd9cf] bg-[#fbfcfa] px-4 py-3 text-base outline-none focus:border-[#6d9e8e] focus:ring-4 focus:ring-[#dcebe5]" placeholder="e.g. Projectile Motion"/><div className="mt-6 rounded-xl bg-[#edf4ee] p-4 text-sm text-[#61746e]">This is a quick check, not the full adaptive lesson. At the end you can choose to learn the topic using the full LearnLens loop.</div>{error&&<div className="mt-4 rounded-xl border border-[#f0cfc7] bg-[#fff3ef] p-3 text-sm text-[#8b463a]">{error}</div>}<div className="mt-7 flex justify-end"><Button onClick={start} disabled={loading||!subject.trim()||!topic.trim()}>{loading?'Building your test...':'Start 5-question test'} <ArrowRight className="size-4"/></Button></div></div></div></Shell>;
  const done=results.length===items.length;
  if(done){const score=Math.round(results.filter(x=>x.correct).length/items.length*100);return <Shell><div className="mx-auto max-w-3xl px-1"><PageHeader eyebrow="Quick result" title={`${score}%`} description={`You got ${results.filter(x=>x.correct).length} of ${items.length} questions correct on ${topic}.`}/><div className="rounded-2xl border border-[#dbe4dc] bg-white p-6 sm:p-8"><p className="text-sm leading-6 text-[#61746e]">This quick check is intentionally separate from the full learning journey. Use the result as a signal, then let LearnLens diagnose and teach the topic.</p><div className="mt-7 flex flex-wrap gap-3"><Button href={`/student/learn?subject=${encodeURIComponent(subject)}&topic=${encodeURIComponent(topic)}`}>Learn this topic <ArrowRight className="size-4"/></Button><Button href="/student" variant="outline">Back to workspace</Button></div></div></div></Shell>}
  const q=items[index];
  return <Shell><div className="mx-auto max-w-3xl px-1"><PageHeader eyebrow="Quick understanding check" title="Test what you know." description={`Question ${index+1} of ${items.length} · ${topic}`} action={<span className="text-xs text-[#82908b]">{results.length} answered</span>}/><div className="rounded-2xl border border-[#dbe4dc] bg-white p-6 sm:p-8"><div className="flex items-center justify-between"><span className="rounded-full bg-[#e5f1ea] px-3 py-1 text-xs font-semibold text-[#39756d]">{q.conceptName||topic}</span><span className="text-xs text-[#82908b]">Difficulty {q.difficulty||2}</span></div><div className="mt-6 rounded-xl bg-[#f6f4ee] p-5"><p className="text-base leading-7 text-[#183e3c]">{q.question}</p></div><div className="mt-5 grid gap-3">{q.options.map((o:string)=><button key={o} onClick={()=>{setAnswer(o);choose(o)}} className={`rounded-xl border p-4 text-left text-sm transition ${answer===o?'border-[#72a68f] bg-[#eaf4ed] text-[#245851]':'border-[#dbe4dc] text-[#61746e] hover:border-[#a8c4b5]'}`}>{o}</button>)}</div><p className="mt-5 text-xs text-[#82908b]">Answers are checked locally against the generated answer key so the interaction stays immediate.</p></div></div></Shell>
}

export default TestPage;
