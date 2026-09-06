const themeToggle=document.querySelector(".theme-toggle");
const applyTheme=theme=>{
  if(window.setTernfoldTheme){window.setTernfoldTheme(theme);return}
  document.documentElement.dataset.theme=theme;
  if(!themeToggle)return;
  const dark=theme==="dark";
  themeToggle.setAttribute("aria-pressed",String(dark));
  themeToggle.setAttribute("aria-label",`Switch to ${dark?"light":"dark"} mode`);
  themeToggle.querySelector(".theme-icon").textContent=dark?"☀":"☾";
  themeToggle.querySelector(".theme-label").textContent=dark?"Light mode":"Dark mode";
};
applyTheme(document.documentElement.dataset.theme||"light");
document.addEventListener("click",async event=>{const account=event.target.closest("[data-email]");if(account){const email=document.querySelector('input[name="email"]');email.value=account.dataset.email;email.focus()}const copy=event.target.closest("[data-copy]");if(copy){const target=document.querySelector(copy.dataset.copy);try{await navigator.clipboard.writeText(target.innerText);const old=copy.textContent;copy.textContent="Handoff copied";setTimeout(()=>copy.textContent=old,1800)}catch{copy.textContent="Copy failed — select the handoff text"}}});
document.querySelectorAll("form").forEach(form=>form.addEventListener("submit",()=>{const button=form.querySelector('button[type="submit"],button:not([type])');if(button&&!button.disabled){button.dataset.label=button.textContent;button.textContent="Saving…";button.setAttribute("aria-busy","true")}}));
const modelContext=document.modelContext;
if(modelContext?.registerTool){
  const register=tool=>{try{Promise.resolve(modelContext.registerTool(tool)).catch(()=>{})}catch{}}
  register({name:"read_visible_case_summary",title:"Read visible case summary",description:"Read the reviewed values, decision and next actor from the currently visible Ternfold case.",inputSchema:{type:"object",properties:{},additionalProperties:false},annotations:{readOnlyHint:true,untrustedContentHint:true},execute:async()=>({caseSummary:document.querySelector("#main")?.innerText.slice(0,4000)||"No case is visible."})});
  register({name:"start_new_case",title:"Start a new case",description:"Open the visible new-case form without creating or saving a case.",inputSchema:{type:"object",properties:{},additionalProperties:false},annotations:{readOnlyHint:false,untrustedContentHint:false},execute:async()=>{location.assign("/cases/new");return{status:"form_opened"}}});
}
