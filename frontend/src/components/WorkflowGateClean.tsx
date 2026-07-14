type Props = {
  canPreview: boolean;
  canExport: boolean;
  hasErrors: boolean;
  mappingPending: boolean;
};

export function WorkflowGateCleanExternal({ canPreview, canExport, hasErrors, mappingPending }: Props) {
  const notes: string[] = [];
  if (!canPreview) notes.push("\u6ca1\u6709\u542f\u7528\u4e14\u517c\u5bb9\u7684 Curve\uff0c\u6682\u65f6\u4e0d\u80fd\u751f\u6210\u9884\u89c8\u3002");
  if (mappingPending) notes.push("\u8bf7\u5148\u786e\u8ba4\u53d8\u91cf\u6620\u5c04\uff0c\u518d\u8fdb\u884c\u6b63\u5f0f\u5bfc\u51fa\u3002");
  if (hasErrors) notes.push("\u5f53\u524d\u5b58\u5728 Error\uff0c\u53ef\u4ee5\u5bfc\u51fa\u8c03\u8bd5\u56fe\uff0c\u4f46\u4e0d\u5e94\u8f93\u51fa\u786e\u5b9a\u6027\u5de5\u7a0b\u7ed3\u8bba\u62a5\u544a\u3002");
  if (!canExport) notes.push("\u6b63\u5f0f\u5bfc\u51fa\u9700\u8981\u5df2\u751f\u6210 Curve\uff0c\u4e14\u5f53\u524d\u56fe\u7c7b\u578b\u4e0b\u81f3\u5c11\u6709\u4e00\u6761\u53ef\u7528\u66f2\u7ebf\u3002");
  if (!notes.length) notes.push("\u5df2\u6ee1\u8db3\u9884\u89c8\u4e0e\u5bfc\u51fa\u7684\u524d\u7f6e\u6761\u4ef6\u3002");

  const ok = notes.length === 1 && canPreview && canExport && !hasErrors;
  return (
    <div className={`rounded-md px-3 py-2 text-xs leading-5 ${ok ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-200" : "bg-amber-50 text-amber-800 dark:bg-amber-400/10 dark:text-amber-100"}`}>
      {notes.map((note) => <div key={note}>{note}</div>)}
    </div>
  );
}
