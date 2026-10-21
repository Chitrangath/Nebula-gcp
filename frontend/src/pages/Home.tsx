export default function Home() {
  return (
    <div className="text-center py-20">
      <h1 className="text-4xl font-bold text-gray-900 mb-4">
        Nebula AI Cloud
      </h1>
      <p className="text-xl text-gray-600 mb-8">
        Trustless AI execution on distributed GPUs. Verify. Pay. Repeat.
      </p>
      <div className="flex justify-center gap-4">
        <a href="/user/submit" className="bg-primary-600 text-white px-6 py-3 rounded-lg hover:bg-primary-700">
          Submit a Job
        </a>
        <a href="/provider/register" className="bg-gray-100 text-gray-900 px-6 py-3 rounded-lg hover:bg-gray-200">
          Become a Provider
        </a>
      </div>
    </div>
  )
}
