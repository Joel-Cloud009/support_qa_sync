-- Supabase SQL Editor에서 실행

create table if not exists support_qa (
  qaidx bigint primary key,
  platform text,
  useridx bigint,
  facebookid text,
  name text,
  contents text,
  device text,
  os_version text,
  mobile_version text,
  writedate timestamp,
  categoryidx integer,
  is_issue_sentence integer
);

create index if not exists idx_support_qa_writedate on support_qa (writedate desc);

-- 검색용 (문의 내용 전문검색)
create extension if not exists pg_trgm;
create index if not exists idx_support_qa_contents_trgm on support_qa using gin (contents gin_trgm_ops);

alter table support_qa enable row level security;

-- 읽기: 누구나(anon key로 프론트에서 검색 가능)
create policy "public read" on support_qa
  for select using (true);

-- 쓰기: service_role만 (GitHub Actions에서 service_role key로 upsert)
-- service_role은 RLS를 우회하므로 별도 정책 불필요
