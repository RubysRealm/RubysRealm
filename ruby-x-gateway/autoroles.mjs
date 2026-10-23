const GUILD='1372700795878899845';
const MEMBER='1563293000833179698';
const OWNER='349665069816348673';
const OWNER_ROLE='1563303966308311130';
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
export function startAutoRoles(token){
 if(!token)return;
 async function api(path,method='GET'){
  for(let attempt=0;attempt<4;attempt++){
   const response=await fetch('https://discord.com/api/v10'+path,{method,headers:{Authorization:'Bot '+token},signal:AbortSignal.timeout(15000)});
   if(response.status===429){const data=await response.json();await sleep(Math.min(60000,Math.ceil((data.retry_after||1)*1000)+200));continue;}
   if(!response.ok)throw Error('Discord status '+response.status);
   return response.status===204?null:response.json();
  }
  throw Error('Discord rate limit');
 }
 async function sync(){
  try{
   let after='0',changed=0;
   for(;;){
    const members=await api('/guilds/'+GUILD+'/members?limit=1000&after='+after);
    for(const member of members){
     if(member.user.bot || member.pending)continue;
     const role=member.user.id===OWNER?OWNER_ROLE:MEMBER;
     if(!member.roles.includes(role)){
      await api('/guilds/'+GUILD+'/members/'+member.user.id+'/roles/'+role,'PUT');changed++;
     }
    }
    if(members.length<1000)break;
    after=members[members.length-1].user.id;
   }
   console.log('Auto roles synchronized; assignments:',changed);
  }catch(error){console.warn('Auto roles will retry:',error.message);}
  setTimeout(sync,30000).unref();
 }
 sync();
}
