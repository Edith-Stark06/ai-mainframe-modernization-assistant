public class IfElseTest {

    private int age;

    public static void main(String[] args) {
        new IfElseTest().run();
    }

    public void run() {

        if (age > 18) {
            System.out.println("ADULT");
        } else {
            System.out.println("MINOR");
        }

    }

}
