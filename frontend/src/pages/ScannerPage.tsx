import ScannerView from '../ScannerView'
import PageHeader from '../components/PageHeader'

export default function ScannerPage() {
  return (
    <>
      <PageHeader
        kicker="MARKET DISCOVERY"
        title="Equity scanner"
        subtitle="Find NSE equities that match technical conditions."
      />
      <ScannerView />
    </>
  )
}
