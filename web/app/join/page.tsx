'use client'

import React, { useState } from 'react'
import Link from 'next/link'
import { ArrowLeft, ArrowRight, LockKeyhole, Users } from 'lucide-react'
import { api } from '@/lib/api'
import { loadState, saveState } from '@/lib/session'
import { Button, Logo } from '@/components/ui-kit'

type JoinResult = { studentId:string; name:string; classCode:string; language:'en'|'kn'|'hi'; synthetic:boolean }

export default function JoinPage(){
  const [name,setName]=useState(''); const [classCode,setClassCode]=useState('CSE-A'); const [language,setLanguage]=useState<'en'|'kn'|'hi'>('en'); const [consent,setConsent]=useState(false); const [busy,setBusy]=useState(false); const [error,setError]=useState(''); const [result,setResult]=useState<JoinResult|null>(null)
  async function submit(e:React.FormEvent){ e.preventDefault();setError('');setBusy(true);try{const data=await api<JoinResult>('/auth/join',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({name:name.trim(),classCode:classCode.trim().toUpperCase(),language,consent})});saveState('learnlens_profile',{...loadState<any>('learnlens_profile',{}),...data});saveState('learnlens_session',{subject:'',topic:'',conceptId:'',conceptName:'',studentId:data.studentId,classCode:data.classCode,language:data.language});setResult(data)}catch(err){setError(err instanceof Error?err.message:'Could not join this class.')}finally{setBusy(false)}}
  return (
    <main className="min-h-screen bg-[#f7f5ef] px-5 py-5 text-[#183e3c] sm:px-8 sm:py-8">
      <header className="mx-auto flex max-w-5xl items-center justify-between">
        <Logo />
        <Link href="/" className="inline-flex min-h-11 items-center gap-2 rounded-xl px-3 text-sm font-medium text-[#61746e] transition hover:bg-[#eaece5] hover:text-[#103c3b] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#39756d]">
          <ArrowLeft className="size-4" />
          Home
        </Link>
      </header>

      <section className="mx-auto mt-8 grid max-w-5xl gap-8 pb-8 sm:mt-12 lg:grid-cols-[0.9fr_1.1fr] lg:items-center">
        <div className="px-1 sm:px-3">
          <div className="mb-5 grid size-12 place-items-center rounded-2xl bg-[#103c3b] text-[#a7cfbc]">
            <Users className="size-6" aria-hidden="true" />
          </div>
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-[#39756d]">LearnLens classroom</p>
          <h1 className="mt-3 max-w-xl font-serif text-4xl leading-[1.08] tracking-[-0.04em] text-[#103c3b] sm:text-5xl">
            See which idea you missed, in your own language, within minutes.
          </h1>
          <p className="mt-5 max-w-lg text-base leading-7 text-[#536762]">
            Join with a nickname and a class code shared by your teacher. No email or password needed.
          </p>
          <div className="mt-6 flex items-start gap-3 rounded-2xl border border-[#dbe4dc] bg-white/70 p-4">
            <LockKeyhole className="mt-0.5 size-5 shrink-0 text-[#39756d]" aria-hidden="true" />
            <p className="text-sm leading-6 text-[#536762]">
              CSE-A is a synthetic sample classroom for demonstrations; its learning data is not from real students.
            </p>
          </div>
        </div>

        <div className="rounded-3xl border border-[#e2e4dc] bg-white p-5 shadow-[0_18px_50px_-35px_rgba(16,60,59,0.35)] sm:p-8">
          {result ? (
            <>
              <div className="rounded-2xl bg-[#edf5ef] p-5">
                <p className="text-sm font-semibold text-[#39756d]">Class joined</p>
                <h2 className="mt-2 font-serif text-3xl text-[#103c3b]">Welcome, {result.name}.</h2>
                <p className="mt-3 text-sm leading-6 text-[#61746e]">
                  You joined <strong>{result.classCode}</strong>. Your browser has saved your LearnLens profile. {result.synthetic ? 'This is the synthetic demo classroom.' : ''}
                </p>
              </div>
              <div className="mt-6 flex flex-col gap-3 sm:flex-row sm:flex-wrap">
                <Button href="/student" className="min-h-12">
                  Open learning workspace <ArrowRight className="size-4" />
                </Button>
                <Button href="/student/privacy" variant="outline" className="min-h-12">
                  Privacy controls
                </Button>
              </div>
            </>
          ) : (
            <>
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[#9b6c3e]">Join a class</p>
              <h2 className="mt-2 font-serif text-3xl tracking-[-0.04em] text-[#103c3b]">Enter your class details</h2>
              <p className="mt-3 text-sm leading-6 text-[#61746e]">
                For a demo, use class code <code className="rounded bg-[#f6f4ee] px-1.5 py-0.5">CSE-A</code>.
              </p>

              <form onSubmit={submit} className="mt-7 space-y-5">
                <div>
                  <label htmlFor="nickname" className="text-sm font-semibold text-[#263d39]">Your name or nickname</label>
                  <input
                    id="nickname"
                    value={name}
                    onChange={e => setName(e.target.value)}
                    required
                    maxLength={50}
                    autoComplete="off"
                    placeholder="For example, Asha"
                    className="mt-2 min-h-12 w-full rounded-xl border border-[#cbd9cf] bg-[#fbfcfa] px-4 py-3 text-base text-[#183e3c] outline-none transition placeholder:text-[#87948f] focus:border-[#6d9e8e] focus-visible:ring-2 focus-visible:ring-[#6d9e8e]/30"
                  />
                  <p className="mt-1 text-xs text-[#758580]">No email, student ID, roll number, or password.</p>
                </div>

                <div>
                  <label htmlFor="classCode" className="text-sm font-semibold text-[#263d39]">Class code</label>
                  <input
                    id="classCode"
                    value={classCode}
                    onChange={e => setClassCode(e.target.value.toUpperCase())}
                    required
                    minLength={3}
                    maxLength={24}
                    placeholder="For example, CSE-A"
                    className="mt-2 min-h-12 w-full rounded-xl border border-[#cbd9cf] bg-[#fbfcfa] px-4 py-3 text-base uppercase text-[#183e3c] outline-none transition placeholder:text-[#87948f] focus:border-[#6d9e8e] focus-visible:ring-2 focus-visible:ring-[#6d9e8e]/30"
                  />
                </div>

                <fieldset>
                  <legend className="text-sm font-semibold text-[#263d39]">Preferred lesson language</legend>
                  <div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-3">
                    <label className={`flex min-h-12 cursor-pointer items-center gap-2 rounded-xl border px-3 py-3 text-sm font-medium transition focus-within:ring-2 focus-within:ring-[#6d9e8e]/40 ${language === 'en' ? 'border-[#39756d] bg-[#edf5ef] text-[#103c3b]' : 'border-[#dbe4dc] bg-[#fbfcfa] text-[#536762] hover:border-[#9eb9ad]'}`}>
                      <input
                        type="radio"
                        name="language"
                        value="en"
                        checked={language === 'en'}
                        onChange={() => setLanguage('en')}
                        className="size-4 accent-[#103c3b]"
                      />
                      English
                    </label>
                    <label className={`flex min-h-12 cursor-pointer items-center gap-2 rounded-xl border px-3 py-3 text-sm font-medium transition focus-within:ring-2 focus-within:ring-[#6d9e8e]/40 ${language === 'kn' ? 'border-[#39756d] bg-[#edf5ef] text-[#103c3b]' : 'border-[#dbe4dc] bg-[#fbfcfa] text-[#536762] hover:border-[#9eb9ad]'}`}>
                      <input
                        type="radio"
                        name="language"
                        value="kn"
                        checked={language === 'kn'}
                        onChange={() => setLanguage('kn')}
                        className="size-4 accent-[#103c3b]"
                      />
                      ಕನ್ನಡ (Kannada)
                    </label>
                    <label className={`flex min-h-12 cursor-pointer items-center gap-2 rounded-xl border px-3 py-3 text-sm font-medium transition focus-within:ring-2 focus-within:ring-[#6d9e8e]/40 ${language === 'hi' ? 'border-[#39756d] bg-[#edf5ef] text-[#103c3b]' : 'border-[#dbe4dc] bg-[#fbfcfa] text-[#536762] hover:border-[#9eb9ad]'}`}>
                      <input
                        type="radio"
                        name="language"
                        value="hi"
                        checked={language === 'hi'}
                        onChange={() => setLanguage('hi')}
                        className="size-4 accent-[#103c3b]"
                      />
                      हिन्दी (Hindi)
                    </label>
                  </div>
                </fieldset>

                <label className="flex min-h-12 cursor-pointer items-start gap-3 rounded-xl border border-[#dbe4dc] bg-[#fbfcfa] p-4 text-sm leading-6 text-[#536762]">
                  <input
                    type="checkbox"
                    checked={consent}
                    onChange={e => setConsent(e.target.checked)}
                    className="mt-1 size-5 shrink-0 accent-[#103c3b] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#6d9e8e]"
                  />
                  <span>I understand LearnLens uses AI, may make mistakes, and stores my answers. I can delete my data any time.</span>
                </label>

                {error && (
                  <p role="alert" className="rounded-xl border border-[#f0cfc7] bg-[#fff3ef] p-3 text-sm text-[#8b463a]">
                    {error}
                  </p>
                )}

                <div className="space-y-3 pt-1">
                  <Button type="submit" disabled={busy || !consent} className="min-h-12 w-full justify-center">
                    {busy ? 'Joining…' : 'Join class'} <ArrowRight className="size-4" />
                  </Button>
                  <button
                    type="button"
                    className="min-h-12 w-full rounded-xl border border-[#cbd9cf] bg-white px-4 py-3 text-sm font-semibold text-[#103c3b] transition hover:bg-[#f5f8f4] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#39756d]"
                  >
                    Try the demo
                  </button>
                </div>
              </form>

              <div className="mt-6 flex flex-col gap-3 border-t border-[#e8ebe5] pt-5 text-sm font-medium sm:flex-row sm:items-center sm:justify-between">
                <Link href="/teacher" className="min-h-11 inline-flex items-center text-[#39756d] underline-offset-4 hover:text-[#103c3b] hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#39756d]">
                  Create a class (teacher)
                </Link>
                <Link href="/student/privacy" className="min-h-11 inline-flex items-center text-[#39756d] underline-offset-4 hover:text-[#103c3b] hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#39756d]">
                  How we use your data
                </Link>
              </div>
            </>
          )}
        </div>
      </section>
    </main>
  )
}
