import autoPost from './auto-post.js';

export default async function handler(req, res) {
  req.headers['x-vercel-cron'] = '1';
  return autoPost(req, res);
}
