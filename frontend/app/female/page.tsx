import Link from "next/link";
import styles from "./page.module.css";
export default function FemaleHome() {
  return <main className={styles.home}>
    <img src="/assets/intro/galstudy_black_title_v1.png" width={1672} height={941} alt="GalStudy" />
    <h1>女性向主界面</h1>
    <Link href="/select">返回</Link>
  </main>;
}
